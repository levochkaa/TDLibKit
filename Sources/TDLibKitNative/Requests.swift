import Foundation
import TDLibCxxBridge

public struct TDLibParameters: Sendable {
    public var useTestDC: Bool
    public var databaseDirectory: String
    public var filesDirectory: String
    public var databaseEncryptionKey: Data
    public var useFileDatabase: Bool
    public var useChatInfoDatabase: Bool
    public var useMessageDatabase: Bool
    public var useSecretChats: Bool
    public var apiID: Int32
    public var apiHash: String
    public var systemLanguageCode: String
    public var deviceModel: String
    public var systemVersion: String
    public var applicationVersion: String

    public init(
        useTestDC: Bool = false,
        databaseDirectory: String,
        filesDirectory: String = "",
        databaseEncryptionKey: Data = Data(),
        useFileDatabase: Bool = true,
        useChatInfoDatabase: Bool = true,
        useMessageDatabase: Bool = true,
        useSecretChats: Bool = true,
        apiID: Int32,
        apiHash: String,
        systemLanguageCode: String,
        deviceModel: String,
        systemVersion: String,
        applicationVersion: String
    ) {
        self.useTestDC = useTestDC
        self.databaseDirectory = databaseDirectory
        self.filesDirectory = filesDirectory
        self.databaseEncryptionKey = databaseEncryptionKey
        self.useFileDatabase = useFileDatabase
        self.useChatInfoDatabase = useChatInfoDatabase
        self.useMessageDatabase = useMessageDatabase
        self.useSecretChats = useSecretChats
        self.apiID = apiID
        self.apiHash = apiHash
        self.systemLanguageCode = systemLanguageCode
        self.deviceModel = deviceModel
        self.systemVersion = systemVersion
        self.applicationVersion = applicationVersion
    }
}

enum NativeRequestDescriptor: Sendable {
    case getOption(String)
    case setLogVerbosityLevel(Int32)
    case setTdlibParameters(TDLibParameters)
    case getChatHistory(
        chatID: Int64,
        fromMessageID: Int64,
        offset: Int32,
        limit: Int32,
        onlyLocal: Bool
    )
    case close

    func makeNative() -> tdlibkit.NativeFunction {
        switch self {
        case .getOption(let name):
            tdlibkit.NativeFunctionFactory.get_option(nativeBuffer(name))
        case .setLogVerbosityLevel(let level):
            tdlibkit.NativeFunctionFactory.set_log_verbosity_level(level)
        case .setTdlibParameters(let parameters):
            tdlibkit.NativeFunctionFactory.set_tdlib_parameters(
                parameters.useTestDC,
                nativeBuffer(parameters.databaseDirectory),
                nativeBuffer(parameters.filesDirectory),
                nativeBuffer(parameters.databaseEncryptionKey),
                parameters.useFileDatabase,
                parameters.useChatInfoDatabase,
                parameters.useMessageDatabase,
                parameters.useSecretChats,
                parameters.apiID,
                nativeBuffer(parameters.apiHash),
                nativeBuffer(parameters.systemLanguageCode),
                nativeBuffer(parameters.deviceModel),
                nativeBuffer(parameters.systemVersion),
                nativeBuffer(parameters.applicationVersion)
            )
        case let .getChatHistory(chatID, fromMessageID, offset, limit, onlyLocal):
            tdlibkit.NativeFunctionFactory.get_chat_history(
                chatID,
                fromMessageID,
                offset,
                limit,
                onlyLocal
            )
        case .close:
            tdlibkit.NativeFunctionFactory.close()
        }
    }
}
