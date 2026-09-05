# Migrating from TDLibKit 1.x

TDLibKit 2 is intentionally source-breaking.

## Removed

- `TDLibFramework` and all JSON C functions;
- `TDLibKitDynamic`;
- `TDLibApi`, `TdApi`, `TdClientImpl`, DTO/Codable models, encoders, and decoders;
- `@extra`/UUID response routing.

## Replacements

Create one actor manager and use its client value:

```swift
let manager = TDLibClientManager()
let client = try await manager.createClient()
```

Use generated typed requests instead of convenience methods or DTO values:

```swift
let result = try await client.send(
    TDNativeRequests.getChatHistory(
        chatId: chatID,
        fromMessageId: 0,
        offset: 0,
        limit: 50,
        onlyLocal: false
    )
)
```

Switch on generated native unions. They contain thin views, not decoded copies:

```swift
for message in result.messages {
    if case .messageText(let content) = message.content {
        print(content.text.text)
    }
}
```

TDLib errors are thrown as `TDLibError`. Updates are delivered through the
client's ordered `AsyncStream<TDNativeUpdate>`. Call `close()` and then manager
`shutdown()` during orderly application termination.

Models are reusable immutable views, including nested objects obtained from
responses. Passing a model to a request or another model's initializer copies
its native subtree for the new owner, preserving the source model and all its
Swift copies. You can retain model values in application state without creating
a fresh native model for every use:

```swift
let list = TDNativeChatList.chatListFolder(.init(chatFolderId: folderID))
let load = TDNativeRequests.loadChats(chatList: list, limit: 200)
let get = TDNativeRequests.getChats(chatList: list, limit: 200)
```

Each `TDRequest` can still be sent only once. Build a new request for retries;
its model parameters can be reused. Explicit `nil` remains valid only for
schema-optional object parameters. Missing required objects and mismatched
native types are rejected before reaching TDLib.

Every target importing TDLibKit must enable Swift C++ interoperability.

If the app and one or more extensions all use TDLibKit, depend on the
`TDLibKitShared` product from every target. Embed it only in the containing app;
extension targets link without embedding and use
`@executable_path/../../Frameworks`. The imported module name remains
`TDLibKit`.

The reference BetterTG migration removes `Packages/TDLibKitDynamic`, links the
shared `TDLibKitShared` product from both application targets, embeds it only in
the containing app, consumes typed native requests/updates, and keeps zero-copy
type aliases for the old model spellings. It is developed on the BetterTG
branch `codex/tdlibkit-2-migration`.
