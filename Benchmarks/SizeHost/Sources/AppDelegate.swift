import TDLibKit
import UIKit

@main
@MainActor
final class AppDelegate: UIResponder, UIApplicationDelegate {
    private let manager = TDLibClientManager()
    private var client: TDClient?

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        Task {
            client = try? await manager.createClient()
        }
        return true
    }
}
