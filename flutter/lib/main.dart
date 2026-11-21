import 'dart:async';
import 'dart:convert';

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:image/image.dart' as img;

import 'capture_file_cleanup_stub.dart'
    if (dart.library.io) 'capture_file_cleanup_io.dart';

const _configuredBrainUrl = String.fromEnvironment('BRAIN_URL');
const _ink = Color(0xFF101713);
const _panel = Color(0xE61A261F);
const _maxUploadWidth = 640;

String get _defaultBrainUrl {
  if (_configuredBrainUrl.isNotEmpty) return _configuredBrainUrl;
  if (kIsWeb) return Uri.base.origin;
  return 'http://127.0.0.1:5000';
}

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const WasteApp());
}

class WasteApp extends StatelessWidget {
  const WasteApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'BinThere',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: _ink,
      colorScheme: ColorScheme.fromSeed(
        seedColor: const Color(0xFF71D49A),
        brightness: Brightness.dark,
      ),
      useMaterial3: true,
    ),
    home: const LiveCameraPage(),
  );
}

class WasteDetection {
  const WasteDetection({
    required this.bin,
    required this.className,
    required this.confidence,
    required this.box,
  });

  final String bin;
  final String className;
  final double confidence;
  final List<double> box;

  static WasteDetection? fromJson(Object? value) {
    if (value is! Map<String, dynamic>) return null;
    final bin = value['bin'];
    final label = value['label'];
    final type = value['type'];
    final confidence = value['conf'];
    final box = value['box'];
    if (bin is! String ||
        label is! String ||
        confidence is! num ||
        box is! List ||
        box.length != 4 ||
        box.any((coordinate) => coordinate is! num)) {
      return null;
    }
    return WasteDetection(
      bin: bin,
      className: type is String ? type : label,
      confidence: confidence.toDouble(),
      box: box.map((coordinate) => (coordinate as num).toDouble()).toList(),
    );
  }
}

class WasteScan {
  const WasteScan({
    required this.detections,
    required this.frameWidth,
    required this.frameHeight,
  });

  final List<WasteDetection> detections;
  final int frameWidth;
  final int frameHeight;

  factory WasteScan.fromJson(Map<String, dynamic> json) => WasteScan(
    detections: (json['detections'] as List? ?? const [])
        .map(WasteDetection.fromJson)
        .whereType<WasteDetection>()
        .toList(growable: false),
    frameWidth: (json['width'] as num?)?.toInt() ?? 0,
    frameHeight: (json['height'] as num?)?.toInt() ?? 0,
  );
}

class LiveCameraPage extends StatefulWidget {
  const LiveCameraPage({super.key});

  @override
  State<LiveCameraPage> createState() => _LiveCameraPageState();
}

class _LiveCameraPageState extends State<LiveCameraPage> {
  CameraController? _controller;
  List<CameraDescription> _cameras = const [];
  WasteScan? _scan;
  String _brainUrl = _defaultBrainUrl;
  String? _cameraError;
  String? _serverError;
  bool _paused = false;
  bool _analyzing = false;
  int _cameraIndex = 0;
  DateTime _lastStreamUpload = DateTime.fromMillisecondsSinceEpoch(0);

  @override
  void initState() {
    super.initState();
    unawaited(_initializeCamera());
  }

  Future<void> _initializeCamera() async {
    try {
      _cameras = await availableCameras().timeout(const Duration(seconds: 12));
      if (_cameras.isEmpty) {
        _setCameraError('No camera was found. Connect a camera and try again.');
        return;
      }
      if (!mounted) return;
      final preferredIndex = _cameras.indexWhere(
        (camera) => camera.lensDirection == CameraLensDirection.back,
      );
      await _startCamera(preferredIndex < 0 ? 0 : preferredIndex);
    } on CameraException catch (error) {
      _setCameraError(_cameraMessage(error));
    } on MissingPluginException {
      _setCameraError(
        'Camera support is not installed for this target. Run flutter pub get, then rebuild the app.',
      );
    } on TimeoutException {
      _setCameraError(
        'Camera discovery timed out. Check that the camera is connected.',
      );
    } catch (error) {
      _setCameraError('Could not find a camera: $error');
    }
  }

  Future<void> _startCamera(int index) async {
    final controller = CameraController(
      _cameras[index],
      // Request a sharper 720p-class preview while keeping Linux inference
      // uploads capped separately at _maxUploadWidth to limit added lag.
      ResolutionPreset.high,
      enableAudio: false,
    );
    if (!mounted) {
      await controller.dispose();
      return;
    }
    setState(() {
      _cameraIndex = index;
      _controller = controller;
      _cameraError = null;
      _scan = null;
    });
    try {
      await controller.initialize().timeout(const Duration(seconds: 20));
      if (!mounted || !identical(_controller, controller)) return;
      setState(() => _cameraError = null);
      if (!kIsWeb && defaultTargetPlatform == TargetPlatform.linux) {
        await controller.startImageStream(
          (frame) => _onLinuxFrame(controller, frame),
        );
      } else {
        unawaited(_analyzeLoop(controller));
      }
    } on CameraException catch (error) {
      if (mounted && identical(_controller, controller)) {
        setState(() {
          _cameraError = _cameraMessage(error);
          _controller = null;
        });
      }
      await controller.dispose();
    } on TimeoutException {
      if (mounted && identical(_controller, controller)) {
        setState(() {
          _cameraError =
              'Camera startup timed out. Check camera access and try again.';
          _controller = null;
        });
      }
      await controller.dispose();
    } catch (error) {
      if (mounted && identical(_controller, controller)) {
        setState(() {
          _cameraError = 'Could not start the camera: $error';
          _controller = null;
        });
      }
      await controller.dispose();
    }
  }

  String _cameraMessage(CameraException error) {
    final message = error.description ?? error.code;
    if (message.toLowerCase().contains('permission') ||
        message.toLowerCase().contains('denied')) {
      return 'Camera access was denied. Allow camera access and restart the app.';
    }
    return 'Could not open the camera: $message';
  }

  void _setCameraError(String message) {
    if (mounted) setState(() => _cameraError = message);
  }

  Future<void> _switchCamera() async {
    if (_cameras.length < 2) return;
    final previous = _controller;
    setState(() {
      _controller = null;
      _scan = null;
    });
    await previous?.dispose();
    if (!mounted) return;
    await _startCamera((_cameraIndex + 1) % _cameras.length);
  }

  Future<void> _analyzeLoop(CameraController controller) async {
    while (mounted && identical(_controller, controller)) {
      if (_paused || !controller.value.isInitialized) {
        await Future<void>.delayed(const Duration(milliseconds: 150));
        continue;
      }

      final timer = Stopwatch()..start();
      XFile? photo;
      if (mounted) setState(() => _analyzing = true);
      try {
        photo = await controller.takePicture();
        final bytes = await photo.readAsBytes();
        await _requestDetection(controller, bytes);
      } catch (error) {
        if (mounted && identical(_controller, controller)) {
          setState(() => _serverError = 'Python detector unavailable: $error');
        }
      } finally {
        if (photo != null) unawaited(cleanupCapturedFile(photo.path));
        if (mounted) setState(() => _analyzing = false);
      }

      final remaining = const Duration(milliseconds: 350) - timer.elapsed;
      if (remaining > Duration.zero) await Future<void>.delayed(remaining);
    }
  }

  void _onLinuxFrame(CameraController controller, CameraImage frame) {
    if (!mounted ||
        _paused ||
        _analyzing ||
        !identical(_controller, controller) ||
        DateTime.now().difference(_lastStreamUpload) <
            const Duration(milliseconds: 220)) {
      return;
    }
    _lastStreamUpload = DateTime.now();
    setState(() => _analyzing = true);
    unawaited(_analyzeLinuxFrame(controller, frame));
  }

  Future<void> _analyzeLinuxFrame(
    CameraController controller,
    CameraImage frame,
  ) async {
    try {
      if (frame.format.group != ImageFormatGroup.bgra8888 ||
          frame.planes.length != 1) {
        throw StateError('Linux camera returned an unsupported frame format.');
      }
      final plane = frame.planes.first;
      final decoded = img.Image.fromBytes(
        width: frame.width,
        height: frame.height,
        bytes: plane.bytes.buffer,
        bytesOffset: plane.bytes.offsetInBytes,
        numChannels: 4,
        rowStride: plane.bytesPerRow,
        order: img.ChannelOrder.bgra,
      );
      final resized = frame.width > _maxUploadWidth
          ? img.copyResize(decoded, width: _maxUploadWidth)
          : decoded;
      final jpeg = Uint8List.fromList(img.encodeJpg(resized, quality: 68));
      await _requestDetection(controller, jpeg);
    } catch (error) {
      if (mounted && identical(_controller, controller)) {
        setState(() => _serverError = 'Live analysis failed: $error');
      }
    } finally {
      if (mounted) setState(() => _analyzing = false);
    }
  }

  Future<void> _requestDetection(
    CameraController controller,
    Uint8List bytes,
  ) async {
    final response = await http
        .post(
          Uri.parse('${_brainUrl.replaceFirst(RegExp(r'/+$'), '')}/predict'),
          headers: const {'Content-Type': 'image/jpeg'},
          body: bytes,
        )
        .timeout(const Duration(seconds: 8));
    if (response.statusCode != 200) {
      throw Exception('Python detector returned HTTP ${response.statusCode}.');
    }
    final data = jsonDecode(utf8.decode(response.bodyBytes));
    if (data is! Map<String, dynamic>) {
      throw const FormatException(
        'Python detector returned an invalid response.',
      );
    }
    if (mounted && identical(_controller, controller)) {
      setState(() {
        _scan = WasteScan.fromJson(data);
        _serverError = null;
      });
    }
  }

  Future<void> _editServerUrl() async {
    final field = TextEditingController(text: _brainUrl);
    final url = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Python detector address'),
        content: TextField(
          controller: field,
          autofocus: true,
          keyboardType: TextInputType.url,
          decoration: const InputDecoration(
            labelText: 'Server URL',
            hintText: 'http://192.168.1.10:5000',
          ),
          onSubmitted: (value) => Navigator.pop(context, value),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, field.text),
            child: const Text('Connect'),
          ),
        ],
      ),
    );
    field.dispose();
    if (url == null || url.trim().isEmpty || !mounted) return;
    setState(() {
      _brainUrl = url.trim().replaceFirst(RegExp(r'/+$'), '');
      _serverError = null;
    });
  }

  @override
  void dispose() {
    final controller = _controller;
    if (controller != null) unawaited(controller.dispose());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;
    final ready = controller?.value.isInitialized == true;
    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(
        fit: StackFit.expand,
        children: [
          if (ready && controller != null)
            _cameraView(controller)
          else
            _cameraPlaceholder(),
          if (ready && _scan != null)
            Positioned.fill(
              child: IgnorePointer(
                child: CustomPaint(painter: _DetectionPainter(_scan!)),
              ),
            ),
          const IgnorePointer(child: _ScreenShade()),
          SafeArea(
            child: Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 8, 14, 8),
                  child: Row(
                    children: [
                      const Icon(
                        Icons.recycling_rounded,
                        color: Color(0xFF75D79C),
                      ),
                      const SizedBox(width: 9),
                      const Text(
                        'BinThere',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const Spacer(),
                      _ConnectionPill(
                        connected: _serverError == null && _scan != null,
                        analyzing: _analyzing,
                      ),
                      IconButton(
                        onPressed: _editServerUrl,
                        tooltip: 'Python server settings',
                        icon: const Icon(
                          Icons.settings_outlined,
                          color: Colors.white,
                        ),
                      ),
                    ],
                  ),
                ),
                const Spacer(),
                _ResultPanel(
                  scan: _scan,
                  error: _serverError,
                  analyzing: _analyzing,
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
                  child: Row(
                    children: [
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: ready
                              ? () => setState(() => _paused = !_paused)
                              : null,
                          icon: Icon(
                            _paused
                                ? Icons.play_arrow_rounded
                                : Icons.pause_rounded,
                          ),
                          label: Text(_paused ? 'Resume scan' : 'Pause scan'),
                          style: OutlinedButton.styleFrom(
                            padding: const EdgeInsets.symmetric(vertical: 14),
                          ),
                        ),
                      ),
                      const SizedBox(width: 10),
                      IconButton.filledTonal(
                        onPressed: _cameras.length > 1 ? _switchCamera : null,
                        tooltip: 'Switch camera',
                        icon: const Icon(Icons.cameraswitch_rounded),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _cameraView(CameraController controller) {
    // Keep the complete camera frame visible. Cover crops the long edges on
    // wide screens and makes the camera look zoomed compared with camera.py.
    return Center(child: CameraPreview(controller));
  }

  Widget _cameraPlaceholder() => Center(
    child: Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (_cameraError == null)
            const CircularProgressIndicator()
          else ...[
            const Icon(
              Icons.no_photography_outlined,
              size: 48,
              color: Colors.white70,
            ),
            const SizedBox(height: 14),
            Text(_cameraError!, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: _initializeCamera,
              icon: const Icon(Icons.refresh_rounded),
              label: const Text('Try again'),
            ),
          ],
        ],
      ),
    ),
  );
}

class _ScreenShade extends StatelessWidget {
  const _ScreenShade();

  @override
  Widget build(BuildContext context) => const DecoratedBox(
    decoration: BoxDecoration(
      gradient: LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [
          Color(0x44000000),
          Colors.transparent,
          Colors.transparent,
          Color(0xD9000000),
        ],
        stops: [0, 0.2, 0.55, 1],
      ),
    ),
  );
}

class _ConnectionPill extends StatelessWidget {
  const _ConnectionPill({required this.connected, required this.analyzing});

  final bool connected;
  final bool analyzing;

  @override
  Widget build(BuildContext context) {
    final color = connected ? const Color(0xFF72E39B) : Colors.orangeAccent;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 7),
      decoration: BoxDecoration(
        color: Colors.black54,
        borderRadius: BorderRadius.circular(24),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.circle, size: 8, color: color),
          const SizedBox(width: 6),
          Text(
            connected
                ? (analyzing ? 'ANALYZING' : 'PYTHON ONLINE')
                : 'CONNECTING',
            style: const TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w800,
              letterSpacing: 0.6,
            ),
          ),
        ],
      ),
    );
  }
}

class _ResultPanel extends StatelessWidget {
  const _ResultPanel({
    required this.scan,
    required this.error,
    required this.analyzing,
  });

  final WasteScan? scan;
  final String? error;
  final bool analyzing;

  @override
  Widget build(BuildContext context) {
    final top = scan != null && scan!.detections.isNotEmpty
        ? scan!.detections.first
        : null;
    final color = top == null ? Colors.white : _binColor(top.bin);
    final title = top == null
        ? (error != null
              ? 'Detector not connected'
              : scan == null
              ? 'Looking for waste…'
              : 'No waste item detected')
        : _binName(top.bin);
    final subtitle = top == null
        ? (error ??
              (scan == null
                  ? 'Flutter camera · Python analysis'
                  : 'Show a waste item to the camera.'))
        : '${top.className.replaceAll('_', ' ')} · ${(top.confidence * 100).round()}% confidence · ${scan!.detections.length} item(s)';
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.symmetric(horizontal: 18),
      padding: const EdgeInsets.fromLTRB(18, 16, 18, 16),
      decoration: BoxDecoration(
        color: _panel,
        border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
        borderRadius: BorderRadius.circular(22),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  title,
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                    color: color,
                  ),
                ),
                const SizedBox(height: 5),
                Text(
                  subtitle,
                  style: const TextStyle(color: Colors.white70, fontSize: 13),
                ),
              ],
            ),
          ),
          if (analyzing)
            const SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
        ],
      ),
    );
  }
}

class _DetectionPainter extends CustomPainter {
  const _DetectionPainter(this.scan);

  final WasteScan scan;

  @override
  void paint(Canvas canvas, Size size) {
    if (scan.frameWidth <= 0 || scan.frameHeight <= 0) return;
    final imageSize = Size(
      scan.frameWidth.toDouble(),
      scan.frameHeight.toDouble(),
    );
    final fitted = applyBoxFit(BoxFit.contain, imageSize, size);
    final source = Alignment.center.inscribe(
      fitted.source,
      Offset.zero & imageSize,
    );
    final destination = Alignment.center.inscribe(
      fitted.destination,
      Offset.zero & size,
    );
    final sx = destination.width / source.width;
    final sy = destination.height / source.height;
    final stroke = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3;

    for (final detection in scan.detections) {
      final rect = Rect.fromLTRB(
        destination.left + (detection.box[0] - source.left) * sx,
        destination.top + (detection.box[1] - source.top) * sy,
        destination.left + (detection.box[2] - source.left) * sx,
        destination.top + (detection.box[3] - source.top) * sy,
      ).intersect(Offset.zero & size);
      if (rect.isEmpty) continue;
      final color = _binColor(detection.bin);
      stroke.color = color;
      canvas.drawRRect(
        RRect.fromRectAndRadius(rect, const Radius.circular(10)),
        stroke,
      );

      final text =
          '${_binName(detection.bin)} ${(detection.confidence * 100).round()}%';
      final painter = TextPainter(
        text: TextSpan(
          text: text,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 12,
            fontWeight: FontWeight.w800,
          ),
        ),
        textDirection: TextDirection.ltr,
      )..layout(maxWidth: size.width);
      final labelRect = Rect.fromLTWH(
        rect.left,
        rect.top >= painter.height + 8
            ? rect.top - painter.height - 8
            : rect.top,
        painter.width + 14,
        painter.height + 8,
      );
      canvas.drawRRect(
        RRect.fromRectAndRadius(labelRect, const Radius.circular(7)),
        Paint()..color = color,
      );
      painter.paint(canvas, Offset(labelRect.left + 7, labelRect.top + 4));
    }
  }

  @override
  bool shouldRepaint(covariant _DetectionPainter oldDelegate) =>
      oldDelegate.scan != scan;
}

String _binName(String code) => switch (code) {
  'biodegradable' => 'Biodegradable',
  'non_biodegradable' => 'Non-biodegradable',
  'residual_special_waste' => 'Residual',
  _ => code.replaceAll('_', ' '),
};

Color _binColor(String code) => switch (code) {
  'biodegradable' => const Color(0xFF54C982),
  'non_biodegradable' => const Color(0xFF55A6D2),
  'residual_special_waste' => const Color(0xFFE59B4A),
  _ => Colors.white,
};
