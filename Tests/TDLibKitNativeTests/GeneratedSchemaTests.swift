import Foundation
import XCTest
@testable import TDLibKit

final class GeneratedSchemaTests: XCTestCase {
    func testGeneratedRequestsRouteTypedResponsesAndBytes() async throws {
        let manager = TDLibClientManager()
        let client = try await manager.createClient()
        try await client.executeSetLogVerbosityLevel(0)

        let option = try await client.send(TDNativeRequests.getOption(name: "version"))
        guard case .optionValueString(let version) = option else {
            return XCTFail("Expected optionValueString")
        }
        XCTAssertEqual(version.value, client.tdlibVersion)

        let bytes = Data([0, 1, 2, 127, 128, 255])
        let bytesResult = try await client.send(TDNativeRequests.testCallBytes(x: bytes))
        XCTAssertEqual(bytesResult.value, bytes)

        let vector = [Int(Int32.min), -1, 0, 1, Int(Int32.max)]
        let vectorResult = try await client.send(TDNativeRequests.testCallVectorInt(x: vector))
        XCTAssertEqual(vectorResult.value, vector)

        try await client.close()
        await manager.shutdown()
    }

    func testGeneratedNestedMessageContentOwnsNativeRoot() throws {
        let formatted = try XCTUnwrap(TDNativeFormattedText.make(text: "native text", entities: []))
        let textContent = try XCTUnwrap(
            TDNativeMessageText.make(
                text: formatted,
                linkPreview: nil,
                linkPreviewOptions: nil
            )
        )
        let content = TDNativeMessageContent.messageText(textContent)
        let sender = TDNativeMessageSender.messageSenderUser(
            TDNativeMessageSenderUser(userId: 1)
        )

        let message = try XCTUnwrap(
            TDNativeMessage.make(
                id: 42,
                senderId: sender,
                receiverId: sender,
                chatId: -100,
                sendingState: nil,
                schedulingState: nil,
                isOutgoing: false,
                isPinned: false,
                isFromOffline: false,
                canBeSaved: true,
                hasTimestampedMedia: false,
                isChannelPost: false,
                isPaidStarSuggestedPost: false,
                isPaidGramSuggestedPost: false,
                containsUnreadMention: false,
                containsUnreadPollVotes: false,
                date: 1,
                editDate: 0,
                forwardInfo: nil,
                importInfo: nil,
                interactionInfo: nil,
                unreadReactions: [],
                factCheck: nil,
                suggestedPostInfo: nil,
                replyTo: nil,
                topicId: nil,
                selfDestructType: nil,
                selfDestructIn: 0,
                autoDeleteIn: 0,
                viaBotUserId: 0,
                guestBotCallerId: nil,
                senderBusinessBotUserId: 0,
                senderBoostCount: 0,
                senderTag: "",
                paidMessageStarCount: 0,
                authorSignature: "",
                mediaAlbumId: 0,
                effectId: 0,
                restrictionInfo: nil,
                summaryLanguageCode: "",
                content: content,
                ephemeralContent: nil,
                replyMarkup: nil,
                ephemeralMessageId: 0,
                chatInstance: 7
            )
        )
        let update = try XCTUnwrap(TDNativeUpdateNewMessage.make(message: message))

        let ownedMessage = update.message
        XCTAssertEqual(ownedMessage.id, 42)
        XCTAssertEqual(ownedMessage.chatId, -100)
        guard case .messageText(let ownedText) = ownedMessage.content else {
            return XCTFail("Expected nested messageText")
        }
        XCTAssertEqual(ownedText.text.text, "native text")
    }

    func testCancellationAndSingleUseRequestOwnership() async throws {
        let manager = TDLibClientManager()
        let client = try await manager.createClient()
        try await client.executeSetLogVerbosityLevel(0)

        let cancelled = Task {
            try Task.checkCancellation()
            return try await client.send(TDNativeRequests.testCallEmpty())
        }
        cancelled.cancel()
        do {
            _ = try await cancelled.value
            XCTFail("Cancelled request unexpectedly completed")
        } catch is CancellationError {
            // Expected.
        }

        let request = TDNativeRequests.getOption(name: "version")
        _ = try await client.send(request)
        do {
            _ = try await client.send(request)
            XCTFail("A native object_ptr request must be consumed exactly once")
        } catch TDLibRuntimeError.requestRejected {
            // Expected.
        }

        if case .string(let version) = try await client.getOption("version") {
            XCTAssertEqual(version, client.tdlibVersion)
        } else {
            XCTFail("Routing failed after cancellation")
        }

        try await client.close()
        await manager.shutdown()
    }
}
