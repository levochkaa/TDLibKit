import Foundation
import TDLibCxxBridge

@inline(__always)
func nativeBuffer(_ value: String) -> tdlibkit.NativeBuffer {
    let bytes = Array(value.utf8)
    return bytes.withUnsafeBufferPointer { buffer in
        tdlibkit.NativeBuffer.copy(buffer.baseAddress, buffer.count)
    }
}

@inline(__always)
func nativeBuffer(_ value: Data) -> tdlibkit.NativeBuffer {
    value.withUnsafeBytes { bytes in
        tdlibkit.NativeBuffer.copy(
            bytes.bindMemory(to: UInt8.self).baseAddress,
            bytes.count
        )
    }
}

@inline(__always)
func swiftData(_ value: tdlibkit.NativeBuffer) -> Data {
    let count = value.size()
    guard count != 0 else { return Data() }
    var data = Data(count: count)
    data.withUnsafeMutableBytes { bytes in
        _ = value.copy_to(bytes.bindMemory(to: UInt8.self).baseAddress, bytes.count)
    }
    return data
}

@inline(__always)
func swiftString(_ value: tdlibkit.NativeBuffer) -> String {
    String(decoding: swiftData(value), as: UTF8.self)
}

func bridgeCompileProbe() {
    var manager = tdlibkit.NativeManager()
    let clientID = manager.create_client_id()
    let request = tdlibkit.NativeFunctionFactory.get_option(nativeBuffer("version"))
    _ = manager.send(clientID, 1, request)
}
