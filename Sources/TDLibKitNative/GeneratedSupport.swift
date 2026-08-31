import Foundation
import TDLibCxxBridge

protocol TDNativeObjectBacked: Sendable {
    var native: NativeOwnedObject { get }
}

public struct TDRequest<Response: Sendable>: @unchecked Sendable {
    private final class Storage: @unchecked Sendable {
        private let lock = NSLock()
        private var make: (@Sendable () -> tdlibkit.NativeFunction)?

        init(make: @escaping @Sendable () -> tdlibkit.NativeFunction) {
            self.make = make
        }

        func take() -> tdlibkit.NativeFunction? {
            lock.lock()
            defer { lock.unlock() }
            guard let make else { return nil }
            self.make = nil
            return make()
        }
    }

    private let storage: Storage
    let decode: @Sendable (NativeOwnedObject) throws -> Response

    init(
        make: @escaping @Sendable () -> tdlibkit.NativeFunction,
        decode: @escaping @Sendable (NativeOwnedObject) throws -> Response
    ) {
        storage = Storage(make: make)
        self.decode = decode
    }

    func takeNative() throws -> tdlibkit.NativeFunction {
        guard let function = storage.take(), function.is_valid() else {
            throw TDLibRuntimeError.requestRejected
        }
        return function
    }
}
