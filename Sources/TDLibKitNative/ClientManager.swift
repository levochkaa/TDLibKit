import Dispatch
import Foundation
import TDLibCxxBridge

private final class NativeResponseBox: @unchecked Sendable {
    let value: tdlibkit.NativeResponse

    init(_ value: tdlibkit.NativeResponse) {
        self.value = value
    }
}

private final class NativeReceivePump: @unchecked Sendable {
    enum State {
        case idle
        case running
        case stopping
        case stopped
    }

    let responses: AsyncStream<NativeResponseBox>

    private var manager: tdlibkit.NativeManager
    private let continuation: AsyncStream<NativeResponseBox>.Continuation
    private let queue = DispatchQueue(label: "app.tdlibkit.native-receive", qos: .utility)
    private let lock = NSLock()
    private var state = State.idle

    init(manager: tdlibkit.NativeManager) {
        self.manager = manager
        let stream = AsyncStream<NativeResponseBox>.makeStream(bufferingPolicy: .unbounded)
        responses = stream.stream
        continuation = stream.continuation
    }

    func start() {
        lock.lock()
        guard state == .idle else {
            lock.unlock()
            return
        }
        state = .running
        lock.unlock()

        queue.async { [weak self] in
            self?.run()
        }
    }

    func stop() {
        lock.lock()
        if state == .idle {
            state = .stopped
            lock.unlock()
            continuation.finish()
            return
        }
        if state == .running {
            state = .stopping
        }
        lock.unlock()
    }

    private func run() {
        while shouldReceive {
            let response = manager.receive(0.25)
            if response.has_object() {
                continuation.yield(NativeResponseBox(response))
            }
        }

        lock.lock()
        state = .stopped
        lock.unlock()
        continuation.finish()
    }

    private var shouldReceive: Bool {
        lock.lock()
        defer { lock.unlock() }
        return state == .running
    }
}

public struct TDClient: Sendable {
    public let id: Int32
    public let tdlibVersion: String
    public let updates: AsyncStream<TDNativeUpdate>

    private let manager: TDLibClientManager

    init(
        id: Int32,
        tdlibVersion: String,
        updates: AsyncStream<TDNativeUpdate>,
        manager: TDLibClientManager
    ) {
        self.id = id
        self.tdlibVersion = tdlibVersion
        self.updates = updates
        self.manager = manager
    }

    public func getOption(_ name: String) async throws -> TDOptionValue {
        try await manager.getOption(name, clientID: id)
    }

    public func executeSetLogVerbosityLevel(_ level: Int32) async throws {
        try await manager.executeSetLogVerbosityLevel(level)
    }

    public func setTdlibParameters(_ parameters: TDLibParameters) async throws {
        try await manager.setTdlibParameters(parameters, clientID: id)
    }

    public func getChatHistory(
        chatID: Int64,
        fromMessageID: Int64 = 0,
        offset: Int32 = 0,
        limit: Int32 = 50,
        onlyLocal: Bool = false
    ) async throws -> TDMessages {
        try await manager.getChatHistory(
            clientID: id,
            chatID: chatID,
            fromMessageID: fromMessageID,
            offset: offset,
            limit: limit,
            onlyLocal: onlyLocal
        )
    }

    public func close() async throws {
        try await manager.closeClient(id)
    }

    public func send<Response: Sendable>(_ request: TDRequest<Response>) async throws -> Response {
        try await manager.send(request, clientID: id)
    }
}

public actor TDLibClientManager {
    private struct PendingRequest {
        let clientID: Int32
        let continuation: CheckedContinuation<NativeOwnedObject, any Swift.Error>
    }

    private struct CloseWaiter {
        let continuation: CheckedContinuation<Void, any Swift.Error>
    }

    private var native: tdlibkit.NativeManager
    private let pump: NativeReceivePump
    private var receiveTask: Task<Void, Never>?
    private var isReceiving = false
    private var acceptingClients = true
    private var isShutDown = false
    private var nextID: UInt64 = 1
    private var pending: [UInt64: PendingRequest] = [:]
    private var updates: [Int32: AsyncStream<TDNativeUpdate>.Continuation] = [:]
    private var closedClients: Set<Int32> = []
    private var closeWaiters: [Int32: [UInt64: CloseWaiter]] = [:]

    public init() {
        let manager = tdlibkit.NativeManager()
        native = manager
        pump = NativeReceivePump(manager: manager)
    }

    deinit {
        pump.stop()
    }

    public func createClient() async throws -> TDClient {
        guard acceptingClients, !isShutDown else {
            throw TDLibRuntimeError.managerShutDown
        }

        let clientID = native.create_client_id()
        guard clientID != 0 else {
            throw TDLibRuntimeError.invalidNativeObject
        }

        let stream = AsyncStream<TDNativeUpdate>.makeStream(bufferingPolicy: .unbounded)
        updates[clientID] = stream.continuation

        do {
            let option = try await request(.getOption("version"), clientID: clientID)
            let value = TDOptionValue(native: option)
            guard case .string(let version) = value else {
                throw TDLibRuntimeError.unexpectedType(
                    expected: "optionValueString",
                    actualTypeID: option.value.type_id()
                )
            }
            return TDClient(
                id: clientID,
                tdlibVersion: version,
                updates: stream.stream,
                manager: self
            )
        } catch {
            updates.removeValue(forKey: clientID)?.finish()
            throw error
        }
    }

    public func closeClients() async {
        await shutdown()
    }

    public func isClientClosed(_ clientID: Int32) -> Bool {
        closedClients.contains(clientID) || updates[clientID] == nil
    }

    public func shutdown() async {
        guard !isShutDown else { return }
        acceptingClients = false

        for clientID in updates.keys.sorted() {
            try? await closeClient(clientID)
        }

        isShutDown = true
        for (_, request) in pending {
            request.continuation.resume(throwing: TDLibRuntimeError.managerShutDown)
        }
        pending.removeAll()

        for continuation in updates.values {
            continuation.finish()
        }
        updates.removeAll()

        for waiters in closeWaiters.values {
            for waiter in waiters.values {
                waiter.continuation.resume(throwing: TDLibRuntimeError.managerShutDown)
            }
        }
        closeWaiters.removeAll()

        pump.stop()
        receiveTask?.cancel()
        receiveTask = nil
    }

    func getOption(_ name: String, clientID: Int32) async throws -> TDOptionValue {
        TDOptionValue(native: try await request(.getOption(name), clientID: clientID))
    }

    func executeSetLogVerbosityLevel(_ level: Int32) throws {
        let result = try execute(.setLogVerbosityLevel(level))
        try expectOK(result)
    }

    func setTdlibParameters(_ parameters: TDLibParameters, clientID: Int32) async throws {
        let result = try await request(.setTdlibParameters(parameters), clientID: clientID)
        try expectOK(result)
    }

    func getChatHistory(
        clientID: Int32,
        chatID: Int64,
        fromMessageID: Int64,
        offset: Int32,
        limit: Int32,
        onlyLocal: Bool
    ) async throws -> TDMessages {
        let result = try await request(
            .getChatHistory(
                chatID: chatID,
                fromMessageID: fromMessageID,
                offset: offset,
                limit: limit,
                onlyLocal: onlyLocal
            ),
            clientID: clientID
        )
        return try TDMessages(native: result)
    }

    func closeClient(_ clientID: Int32) async throws {
        if closedClients.contains(clientID) {
            return
        }

        let result = try await request(.close, clientID: clientID)
        try expectOK(result)

        if closedClients.contains(clientID) {
            return
        }

        let waiterID = try allocateID()
        try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation {
                (continuation: CheckedContinuation<Void, any Swift.Error>) in
                if Task.isCancelled {
                    continuation.resume(throwing: CancellationError())
                    return
                }
                closeWaiters[clientID, default: [:]][waiterID] = CloseWaiter(
                    continuation: continuation
                )
            }
        } onCancel: {
            Task { await self.cancelCloseWaiter(clientID: clientID, waiterID: waiterID) }
        }
    }

    func send<Response: Sendable>(
        _ typedRequest: TDRequest<Response>,
        clientID: Int32
    ) async throws -> Response {
        let object = try await request(try typedRequest.takeNative(), clientID: clientID)
        return try typedRequest.decode(object)
    }

    private func request(
        _ descriptor: NativeRequestDescriptor,
        clientID: Int32
    ) async throws -> NativeOwnedObject {
        try await request(descriptor.makeNative(), clientID: clientID)
    }

    private func request(
        _ function: tdlibkit.NativeFunction,
        clientID: Int32
    ) async throws -> NativeOwnedObject {
        guard !isShutDown else {
            throw TDLibRuntimeError.managerShutDown
        }

        let requestID = try allocateID()
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                if Task.isCancelled {
                    continuation.resume(throwing: CancellationError())
                    return
                }

                pending[requestID] = PendingRequest(
                    clientID: clientID,
                    continuation: continuation
                )

                let accepted = native.send(clientID, requestID, function)
                guard accepted else {
                    pending.removeValue(forKey: requestID)?.continuation.resume(
                        throwing: TDLibRuntimeError.requestRejected
                    )
                    return
                }
                startReceivingIfNeeded()
            }
        } onCancel: {
            Task { await self.cancelRequest(requestID) }
        }
    }

    private func execute(_ descriptor: NativeRequestDescriptor) throws -> NativeOwnedObject {
        guard !isShutDown else {
            throw TDLibRuntimeError.managerShutDown
        }
        let object = NativeOwnedObject(
            value: tdlibkit.NativeManager.execute(descriptor.makeNative())
        )
        guard object.value.is_valid() else {
            throw TDLibRuntimeError.invalidNativeObject
        }
        if let error = TDLibError(native: object) {
            throw error
        }
        return object
    }

    private func expectOK(_ object: NativeOwnedObject) throws {
        guard object.value.kind() == .ok else {
            throw TDLibRuntimeError.unexpectedType(
                expected: "ok",
                actualTypeID: object.value.type_id()
            )
        }
    }

    private func allocateID() throws -> UInt64 {
        guard nextID != 0 else {
            throw TDLibRuntimeError.requestIDExhausted
        }
        let result = nextID
        if nextID == UInt64.max {
            nextID = 0
        } else {
            nextID += 1
        }
        return result
    }

    private func startReceivingIfNeeded() {
        guard !isReceiving else { return }
        isReceiving = true
        let responses = pump.responses
        receiveTask = Task { [weak self] in
            for await response in responses {
                guard let self else { return }
                await self.handle(response.value)
            }
        }
        pump.start()
    }

    private func handle(_ response: tdlibkit.NativeResponse) {
        let clientID = response.client_id()
        let requestID = response.request_id()
        let object = NativeOwnedObject(value: response.object())

        if requestID != 0 {
            guard let request = pending.removeValue(forKey: requestID) else { return }
            guard request.clientID == clientID else {
                request.continuation.resume(
                    throwing: TDLibRuntimeError.responseClientMismatch(
                        expected: request.clientID,
                        actual: clientID
                    )
                )
                return
            }
            if let error = TDLibError(native: object) {
                request.continuation.resume(throwing: error)
            } else {
                request.continuation.resume(returning: object)
            }
            return
        }

        guard let continuation = updates[clientID] else { return }
        guard let update = TDNativeUpdate(native: object) else { return }
        continuation.yield(update)

        let isClosed: Bool
        if case .updateAuthorizationState(let authorizationUpdate) = update,
           case .authorizationStateClosed = authorizationUpdate.authorizationState
        {
            isClosed = true
        } else {
            isClosed = false
        }

        if isClosed {
            closedClients.insert(clientID)
            updates.removeValue(forKey: clientID)?.finish()
            let waiters = closeWaiters.removeValue(forKey: clientID) ?? [:]
            for waiter in waiters.values {
                waiter.continuation.resume()
            }
        }
    }

    private func cancelRequest(_ requestID: UInt64) {
        pending.removeValue(forKey: requestID)?.continuation.resume(
            throwing: CancellationError()
        )
    }

    private func cancelCloseWaiter(clientID: Int32, waiterID: UInt64) {
        closeWaiters[clientID]?.removeValue(forKey: waiterID)?.continuation.resume(
            throwing: CancellationError()
        )
        if closeWaiters[clientID]?.isEmpty == true {
            closeWaiters.removeValue(forKey: clientID)
        }
    }
}
