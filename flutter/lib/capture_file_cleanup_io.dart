import 'dart:io';

Future<void> cleanupCapturedFile(String path) async {
  try {
    final file = File(path);
    if (await file.exists()) await file.delete();
  } on FileSystemException {
    // Temporary-file cleanup should never interrupt a scan.
  }
}
