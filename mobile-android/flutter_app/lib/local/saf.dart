import 'dart:convert';

import 'package:flutter/services.dart';

import 'local_agent.dart';

/// Storage Access Framework bridge (Android). Picks/saves through the system
/// document UI so internal storage, SD card, Google Drive and a plugged-in USB
/// drive all work with no extra plugin.
class Saf {
  static const _ch = MethodChannel('vajra/files');

  /// User picks one or more text files. Returns [] if cancelled.
  static Future<List<LocalFile>> openFiles() async {
    final raw = await _ch.invokeMethod<List<dynamic>>('openFiles');
    if (raw == null) return [];
    return [
      for (final e in raw)
        LocalFile((e as Map)['name'] as String, e['content'] as String),
    ];
  }

  /// User picks where to save; returns the chosen file name, or null if cancelled.
  static Future<String?> saveFile(String name, String content) {
    return _ch.invokeMethod<String>('saveFile', {
      'name': name,
      'bytes': Uint8List.fromList(utf8.encode(content)),
    });
  }
}
