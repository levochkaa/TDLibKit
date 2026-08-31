import TDLibKit
import UIKit

@main
@MainActor
final class AppDelegate: UIResponder, UIApplicationDelegate {
    private let manager = TDLibClientManager()
    private var client: TDLibClient?

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        let client = manager.createClient { _, _ in }
        self.client = client
        Task {
            _ = try? await client.getOption(name: "version")
        }
        return true
    }
}
