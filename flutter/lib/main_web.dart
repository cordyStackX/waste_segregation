// ignore_for_file: avoid_web_libraries_in_flutter, deprecated_member_use
import 'dart:html' as html;
import 'dart:ui_web' as ui_web;

import 'package:flutter/material.dart';

void main() {
  // The Flask detector page lives at "/" on the same server/origin,
  // so the HTTPS certificate and camera permission are shared.
  ui_web.platformViewRegistry.registerViewFactory('detector-iframe', (int id) {
    return html.IFrameElement()
      ..src = '/'
      ..allow = 'camera; microphone'
      ..style.border = 'none'
      ..style.width = '100%'
      ..style.height = '100%';
  });

  runApp(const WasteApp());
}

class WasteApp extends StatelessWidget {
  const WasteApp({super.key});

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Waste Detector',
      home: Scaffold(
        backgroundColor: Color(0xFF111111),
        body: SafeArea(
          child: HtmlElementView(viewType: 'detector-iframe'),
        ),
      ),
    );
  }
}