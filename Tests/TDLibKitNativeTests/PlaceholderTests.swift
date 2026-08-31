import XCTest
@testable import TDLibKit

final class PlaceholderTests: XCTestCase {
    func testMajorVersion() {
        XCTAssertEqual(TDLibKitVersion.major, 2)
    }
}
