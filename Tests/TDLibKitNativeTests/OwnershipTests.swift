import Foundation
import TDLibCxxBridge
import XCTest
@testable import TDLibKit

final class OwnershipTests: XCTestCase {
    func testChatListParametersSurviveDifferentRequestsAndCopies() async throws {
        let manager = TDLibClientManager()
        let client = try await manager.createClient()
        try await client.executeSetLogVerbosityLevel(0)
        let folder = TDNativeChatListFolder(chatFolderId: 23)
        let copy = folder
        let list = TDNativeChatList.chatListFolder(folder)

        // TDLib may reject these before authorization, but it must receive
        // each request without invalidating the application's model values.
        await assertReachesTDLib(TDNativeRequests.loadChats(chatList: list, limit: 200), client: client)
        XCTAssertEqual(folder.chatFolderId, 23)
        XCTAssertEqual(copy.chatFolderId, 23)
        await assertReachesTDLib(TDNativeRequests.getChats(chatList: list, limit: 200), client: client)
        await assertReachesTDLib(TDNativeRequests.getChats(chatList: .chatListFolder(copy), limit: 50), client: client)
        XCTAssertEqual(folder.chatFolderId, 23)
        XCTAssertEqual(copy.chatFolderId, 23)
        try await client.close()
        await manager.shutdown()
    }

    func testSameObjectCanAppearInMultipleFieldsAndVectorElements() {
        let folder = TDNativeChatListFolder(chatFolderId: 23)
        let list = TDNativeChatList.chatListFolder(folder)
        let position = TDNativeChatPosition(list: list, order: .max, isPinned: true, source: nil)
        let lists = TDNativeChatLists(chatLists: [list, list, position.list])

        XCTAssertEqual(folder.chatFolderId, 23)
        XCTAssertEqual(position.order, .max)
        XCTAssertTrue(position.isPinned)
        XCTAssertNil(position.source)
        XCTAssertEqual(lists.chatLists.count, 3)
        XCTAssertEqual(lists.chatLists.map(folderID), [23, 23, 23])
    }

    func testChildOutlivesParentAndCanBecomeAnInput() async throws {
        let child: TDNativeFormattedText = {
            let text = TDNativeFormattedText(text: "hello", entities: [])
            let parent = TDNativeMessageText(text: text, linkPreview: nil, linkPreviewOptions: nil)
            return parent.text
        }()

        let input = TDNativeInputMessageText(text: child, linkPreviewOptions: nil, clearDraft: true)
        XCTAssertEqual(input.text.text, "hello")
        XCTAssertTrue(input.clearDraft)
        XCTAssertNil(input.linkPreviewOptions)
        let manager = TDLibClientManager()
        let client = try await manager.createClient()
        let parsed = try await client.send(TDNativeRequests.parseMarkdown(text: child))
        XCTAssertEqual(parsed.text, "hello")
        XCTAssertEqual(child.text, "hello")
        try await client.close()
        await manager.shutdown()
    }

    func testNestedVectorsAndBytesAreCopiedThroughParentObjects() {
        let bytes = Data([0, 1, 127, 128, 255])
        let callback = TDNativeInlineKeyboardButtonTypeCallback(data: bytes)
        let button = TDNativeInlineKeyboardButton(
            text: "Go",
            iconCustomEmojiId: .max,
            style: .buttonStyleDefault,
            type: .inlineKeyboardButtonTypeCallback(callback)
        )
        let markup = TDNativeReplyMarkupInlineKeyboard(rows: [[button, button], [], [button]], forceReply: true)
        let text = TDNativeMessageText(
            text: TDNativeFormattedText(text: "hello", entities: []),
            linkPreview: nil,
            linkPreviewOptions: nil
        )
        let parent = TDNativeEphemeralMessageContent(
            canBeSaved: true,
            hasTimestampedMedia: false,
            content: .messageText(text),
            replyMarkup: .replyMarkupInlineKeyboard(markup)
        )

        guard case .replyMarkupInlineKeyboard(let ownedMarkup) = parent.replyMarkup else {
            return XCTFail("Expected the nested inline keyboard")
        }
        XCTAssertEqual(ownedMarkup.rows.map(\.count), [2, 0, 1])
        XCTAssertTrue(ownedMarkup.forceReply)
        for item in ownedMarkup.rows.flatMap({ $0 }) {
            XCTAssertEqual(item.text, "Go")
            XCTAssertEqual(item.iconCustomEmojiId, .max)
            guard case .inlineKeyboardButtonTypeCallback(let ownedCallback) = item.type else {
                return XCTFail("Expected callback data")
            }
            XCTAssertEqual(ownedCallback.data, bytes)
        }
        XCTAssertEqual(callback.data, bytes)
        XCTAssertEqual(button.text, "Go")
        XCTAssertEqual(markup.rows.map(\.count), [2, 0, 1])
        XCTAssertEqual(text.text.text, "hello")
    }

    func testBridgeRejectsMissingRequiredObjectsAndWrongTypes() {
        var missingText = tdlibkit.NativeArguments()
        missingText.append_object(tdlibkit.NativeObject())
        missingText.append_object(tdlibkit.NativeObject())
        missingText.append_bool(false)
        XCTAssertFalse(tdlibkit.NativeSchemaFactory.make_object(
            TDNativeInputMessageText.typeID, missingText
        ).is_valid())

        // Null chat_list is explicitly supported by getChats.
        var optionalList = tdlibkit.NativeArguments()
        optionalList.append_object(tdlibkit.NativeObject())
        optionalList.append_int32(10)
        let getChatsTypeID: Int32 = -972768574 // From the pinned td_api schema.
        XCTAssertTrue(tdlibkit.NativeSchemaFactory.make_function(getChatsTypeID, optionalList).is_valid())

        var stringArguments = tdlibkit.NativeArguments()
        stringArguments.append_buffer(tdlibkit.NativeBuffer())
        let wrongObject = tdlibkit.NativeSchemaFactory.make_object(TDNativeTestString.typeID, stringArguments)
        var wrongList = tdlibkit.NativeArguments()
        wrongList.append_object(wrongObject)
        wrongList.append_int32(10)
        XCTAssertFalse(tdlibkit.NativeSchemaFactory.make_function(getChatsTypeID, wrongList).is_valid())
        XCTAssertTrue(wrongObject.is_valid())

        var values = tdlibkit.NativeObjectArray()
        values.append(tdlibkit.NativeObject())
        var invalidVector = tdlibkit.NativeArguments()
        invalidVector.append_object_vector(values)
        XCTAssertFalse(tdlibkit.NativeSchemaFactory.make_object(
            TDNativeChatLists.typeID, invalidVector
        ).is_valid())
    }

    func testResponseObjectsCanBeSentAgainAndDuplicated() async throws {
        let manager = TDLibClientManager()
        let client = try await manager.createClient()
        try await client.executeSetLogVerbosityLevel(0)
        let value = TDNativeTestString(value: "native \u{0} text 🐈")
        let first = try await client.send(TDNativeRequests.testCallVectorStringObject(x: [value, value]))
        XCTAssertEqual(first.value.map(\.value), [value.value, value.value])
        XCTAssertEqual(value.value, "native \u{0} text 🐈")

        let received = try XCTUnwrap(first.value.first)
        let second = try await client.send(TDNativeRequests.testCallVectorStringObject(x: [received, received]))
        XCTAssertEqual(second.value.map(\.value), ["native \u{0} text 🐈", "native \u{0} text 🐈"])
        XCTAssertEqual(first.value.map(\.value), second.value.map(\.value))

        try await client.close()
        await manager.shutdown()
    }

    func testSharedModelsCanBeReadWhileBuildingParentsConcurrently() async {
        let folder = TDNativeChatListFolder(chatFolderId: 23)
        let list = TDNativeChatList.chatListFolder(folder)
        await withTaskGroup(of: Bool.self) { group in
            for _ in 0..<64 {
                group.addTask {
                    let position = TDNativeChatPosition(list: list, order: 1, isPinned: false, source: nil)
                    let lists = TDNativeChatLists(chatLists: [position.list, list])
                    guard lists.chatLists.count == 2,
                          case .chatListFolder(let first) = lists.chatLists[0],
                          case .chatListFolder(let second) = lists.chatLists[1] else {
                        return false
                    }
                    return first.chatFolderId == 23 && second.chatFolderId == 23 && folder.chatFolderId == 23
                }
            }
            for await success in group {
                XCTAssertTrue(success)
            }
        }
        XCTAssertEqual(folder.chatFolderId, 23)
    }

    private func folderID(_ list: TDNativeChatList) -> Int? {
        guard case .chatListFolder(let folder) = list else { return nil }
        return folder.chatFolderId
    }

    private func assertReachesTDLib<Response>(
        _ request: TDRequest<Response>, client: TDClient
    ) async {
        do {
            _ = try await client.send(request)
        } catch is TDLibError {
            // Expected for requests that require authorization.
        } catch {
            XCTFail("Request rejected before reaching TDLib: \(error)")
        }
    }
}
