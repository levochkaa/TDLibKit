# ADR: native C++ TDLibKit 2

## Decision

TDLibKit 2 uses upstream `td::ClientManager` and `td_api::object_ptr` through a
small C++ façade. The Swift target imports only `TDLibCxxBridge` with C++
interoperability enabled. The final application linker consumes a static TDLib
archive so dead stripping happens at the host-app boundary.

The package publishes two products over the same module: canonical static
`TDLibKit` and opt-in dynamic `TDLibKitShared`. Static linkage remains the size
default for a single executable. A containing app with extensions may embed one
`TDLibKitShared.framework`; extensions link it through their containing-app
runpath and must not embed additional copies. The shared product intentionally
trades per-executable final-linker dead stripping for one framework shared by
all executables in the application bundle.

The bridge hides TDLib inheritance, templates, and rvalue references. Copyable
Swift-importable RAII handles share a native root owner. Child handles are alias
views whose root remains alive; no C++ pointer is returned to Swift. Input
objects are consumed once and moved into TDLib objects after exhaustive type-ID
validation. All exported bridge methods are `noexcept`, and the bridge is built
with C++ exceptions and RTTI disabled.

## Concurrency

`TDLibClientManager` is an actor. It serializes client state, request maps, and
owned objects. A dedicated queue performs the sole concurrent `receive(0.25)`
call and yields responses into one `AsyncStream`, preserving receive order.
Responses use non-zero `UInt64` request IDs; updates use zero. Cancellation
removes and resumes pending continuations. Closing waits for
`authorizationStateClosed`, finishes the update stream, and releases the client.

## Schema generation

The generator parses every declaration from pinned `td_api.tl`, validates type
IDs against TDLib's officially generated `td_api.h`, and emits deterministic
schema IR, exhaustive safe C++ field access/factories, and thin Swift views,
unions, constructors, and typed requests.

The generated graph covers scalar values, vectors, nested vectors, bytes,
int53, and Int64 without Codable or JSON transport. Object nullability comes
from the matching `//@field` documentation in pinned `td_api.tl`; 592 object
fields explicitly mention null and remain optional. Required fields fail fast
if the native contract is violated. TL `int32` is Swift `Int` at the façade and
uses an exact checked conversion only when entering C++.

## Size decision

Release `-Oz`, static-only, `BUILD_TESTING=OFF`, hidden TD symbols, host
dead-strip, and stripped output is the selected configuration. The full-schema
installed host measured 30,983,288 bytes with Release `-O3`, 25,546,472 with
MinSizeRel `-Os`, and 22,340,824 with Release `-Oz`.
ThinLTO is not selected yet because the raw bitcode archive is not accepted by
the raw-library XCFramework creator. App-bundle measurements, not archive or
repository size, decide the configuration.
