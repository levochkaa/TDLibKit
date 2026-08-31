import TDLibCxxBridge

struct NativeOwnedObject: @unchecked Sendable {
    let value: tdlibkit.NativeObject
}

public struct TDUnknownObject: @unchecked Sendable {
    let native: NativeOwnedObject

    public var typeID: Int32 {
        native.value.type_id()
    }
}

public struct TDLibError: Swift.Error, Equatable, Sendable {
    public let code: Int32
    public let message: String

    public init(code: Int32, message: String) {
        self.code = code
        self.message = message
    }

    init?(native: NativeOwnedObject) {
        guard native.value.kind() == .error else { return nil }
        self.init(
            code: native.value.int32_value(.error_code),
            message: swiftString(native.value.string_value(.error_message))
        )
    }
}

public enum TDLibRuntimeError: Swift.Error, Equatable, Sendable {
    case invalidNativeObject
    case unexpectedType(expected: String, actualTypeID: Int32)
    case requestIDExhausted
    case requestRejected
    case responseClientMismatch(expected: Int32, actual: Int32)
    case managerShutDown
}

public enum TDOptionValue: Sendable {
    case string(String)
    case unknown(TDUnknownObject)

    init(native: NativeOwnedObject) {
        if native.value.kind() == .option_value_string {
            self = .string(swiftString(native.value.string_value(.option_value_string)))
        } else {
            self = .unknown(TDUnknownObject(native: native))
        }
    }
}

public enum TDAuthorizationState: Sendable {
    case waitTdlibParameters
    case waitPhoneNumber
    case ready
    case loggingOut
    case closing
    case closed
    case unknown(TDUnknownObject)

    init(native: NativeOwnedObject) {
        switch native.value.kind() {
        case .authorization_state_wait_tdlib_parameters:
            self = .waitTdlibParameters
        case .authorization_state_wait_phone_number:
            self = .waitPhoneNumber
        case .authorization_state_ready:
            self = .ready
        case .authorization_state_logging_out:
            self = .loggingOut
        case .authorization_state_closing:
            self = .closing
        case .authorization_state_closed:
            self = .closed
        default:
            self = .unknown(TDUnknownObject(native: native))
        }
    }
}

public struct TDFormattedText: @unchecked Sendable {
    let native: NativeOwnedObject

    public var text: String {
        swiftString(native.value.string_value(.formatted_text))
    }
}

public enum TDMessageContent: Sendable {
    case text(TDFormattedText)
    case unknown(TDUnknownObject)

    init(native: NativeOwnedObject) {
        if native.value.kind() == .message_text {
            let text = NativeOwnedObject(value: native.value.child(.message_text_text))
            if text.value.is_valid(), text.value.kind() == .formatted_text {
                self = .text(TDFormattedText(native: text))
                return
            }
        }
        self = .unknown(TDUnknownObject(native: native))
    }
}

public struct TDMessage: @unchecked Sendable {
    let native: NativeOwnedObject

    public var id: Int64 {
        native.value.int64_value(.message_id)
    }

    public var chatID: Int64 {
        native.value.int64_value(.message_chat_id)
    }

    public var content: TDMessageContent {
        let content = NativeOwnedObject(value: native.value.child(.message_content))
        guard content.value.is_valid() else {
            return .unknown(TDUnknownObject(native: content))
        }
        return TDMessageContent(native: content)
    }
}

public struct TDMessages: @unchecked Sendable {
    let native: NativeOwnedObject

    init(native: NativeOwnedObject) throws {
        guard native.value.kind() == .messages else {
            throw TDLibRuntimeError.unexpectedType(
                expected: "messages",
                actualTypeID: native.value.type_id()
            )
        }
        self.native = native
    }

    public var totalCount: Int32 {
        native.value.int32_value(.messages_total_count)
    }

    public var messages: [TDMessage] {
        let count = native.value.object_count(.messages)
        return (0..<count).compactMap { index in
            let object = NativeOwnedObject(value: native.value.object_at(.messages, index))
            guard object.value.kind() == .message else { return nil }
            return TDMessage(native: object)
        }
    }
}

public enum TDUpdate: Sendable {
    case authorizationState(TDAuthorizationState)
    case newMessage(TDMessage)
    case unknown(TDUnknownObject)

    init(native: NativeOwnedObject) {
        switch native.value.kind() {
        case .update_authorization_state:
            let state = NativeOwnedObject(value: native.value.child(.update_authorization_state))
            self = .authorizationState(TDAuthorizationState(native: state))
        case .update_new_message:
            let message = NativeOwnedObject(value: native.value.child(.update_new_message))
            if message.value.is_valid(), message.value.kind() == .message {
                self = .newMessage(TDMessage(native: message))
            } else {
                self = .unknown(TDUnknownObject(native: native))
            }
        default:
            self = .unknown(TDUnknownObject(native: native))
        }
    }
}
