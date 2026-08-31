import XCTest
@testable import TDLibKit

final class VerticalSliceTests: XCTestCase {
    func testAuthorizationParametersAndTypedError() async throws {
        let manager = TDLibClientManager()
        let client = try await clientWithinTimeout(manager: manager)
        try await client.executeSetLogVerbosityLevel(0)

        let databaseURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("tdlibkit-native-auth-\(ProcessInfo.processInfo.processIdentifier)")
        let parameters = TDLibParameters(
            databaseDirectory: databaseURL.path,
            apiID: 1,
            apiHash: "not-a-secret-test-hash",
            systemLanguageCode: "en",
            deviceModel: "TDLibKitTests",
            systemVersion: "macOS",
            applicationVersion: "2.0.0"
        )

        try await client.setTdlibParameters(parameters)
        let state = try await authorizationStateWithinTimeout(updates: client.updates)
        guard case .authorizationStateWaitPhoneNumber = state else {
            return XCTFail("Expected waitPhoneNumber, got \(state)")
        }

        do {
            _ = try await client.getChatHistory(chatID: 0, onlyLocal: true)
            XCTFail("getChatHistory must fail before authorization")
        } catch let error as TDLibError {
            XCTAssertNotEqual(error.code, 0)
            XCTAssertFalse(error.message.isEmpty)
        }

        try await client.close()
        await manager.shutdown()
    }

    func testCreateVersionExecuteAndClose() async throws {
        let manager = TDLibClientManager()
        let client = try await clientWithinTimeout(manager: manager)

        XCTAssertFalse(client.tdlibVersion.isEmpty)
        if case .string(let version) = try await client.getOption("version") {
            XCTAssertEqual(version, client.tdlibVersion)
        } else {
            XCTFail("version must be optionValueString")
        }

        try await client.executeSetLogVerbosityLevel(0)
        try await client.close()
        await manager.shutdown()
    }

    private func clientWithinTimeout(manager: TDLibClientManager) async throws -> TDClient {
        try await withThrowingTaskGroup(of: TDClient.self) { group in
            group.addTask {
                try await manager.createClient()
            }
            group.addTask {
                try await Task.sleep(nanoseconds: 15_000_000_000)
                throw TestTimeout()
            }
            let client = try await group.next()!
            group.cancelAll()
            return client
        }
    }

    private func authorizationStateWithinTimeout(
        updates: AsyncStream<TDNativeUpdate>
    ) async throws -> TDNativeAuthorizationState {
        try await withThrowingTaskGroup(of: TDNativeAuthorizationState.self) { group in
            group.addTask {
                for await update in updates {
                    if case .updateAuthorizationState(let value) = update,
                       case .authorizationStateWaitPhoneNumber = value.authorizationState {
                        let state = value.authorizationState
                        return state
                    }
                }
                throw TestTimeout()
            }
            group.addTask {
                try await Task.sleep(nanoseconds: 20_000_000_000)
                throw TestTimeout()
            }
            let state = try await group.next()!
            group.cancelAll()
            return state
        }
    }
}

final class MultiClientTests: XCTestCase {
    func testFiftyClientsShareOneReceivePumpAndRouteResponses() async throws {
        let manager = TDLibClientManager()
        let first = try await manager.createClient()
        try await first.executeSetLogVerbosityLevel(0)

        var clients = [first]
        clients += try await withThrowingTaskGroup(of: TDClient.self) { group in
            for _ in 1..<50 {
                group.addTask {
                    try await manager.createClient()
                }
            }

            var result: [TDClient] = []
            for try await client in group {
                result.append(client)
            }
            return result
        }

        XCTAssertEqual(clients.count, 50)
        XCTAssertEqual(Set(clients.map(\.id)).count, 50)
        XCTAssertTrue(clients.allSatisfy { $0.tdlibVersion == first.tdlibVersion })

        try await withThrowingTaskGroup(of: Void.self) { group in
            for client in clients {
                group.addTask {
                    try await client.close()
                }
            }
            try await group.waitForAll()
        }
        await manager.shutdown()
    }
}

private struct TestTimeout: Swift.Error {}
