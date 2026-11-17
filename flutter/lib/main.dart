import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';

const serverUrl = 'https://192.168.1.50:5000';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Permission.camera.request();
  runApp(const MaterialApp(debugShowCheckedModeBanner: false, home: DetectorPage()));
}

class DetectorPage extends StatefulWidget {
  const DetectorPage({super.key});
  @override
  State<DetectorPage> createState() => _DetectorPageState();
}

class _DetectorPageState extends State<DetectorPage> {
  late final WebViewController c;

  @override
  void initState() {
    super.initState();
    c = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(NavigationDelegate(
        // accept the self-signed cert from Flask's ssl_context="adhoc" (Android)
        onSslAuthError: (error) => error.proceed(),
      ))
      ..loadRequest(Uri.parse(serverUrl));

    final p = c.platform;
    if (p is AndroidWebViewController) {
      p.setMediaPlaybackRequiresUserGesture(false);
      p.setOnPlatformPermissionRequest((req) => req.grant()); // allow getUserMedia
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        body: SafeArea(child: WebViewWidget(controller: c)),
      );
}