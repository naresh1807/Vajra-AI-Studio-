import 'dart:convert';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../github/gh_store.dart';
import '../github/nim.dart';
import 'local_agent.dart';

/// "Files on this device" mode: pick files (internal storage, SD card, Google
/// Drive, a plugged-in USB drive - anything Android's file picker exposes),
/// let the model edit them, then save each result wherever you choose.
class LocalModeApp extends StatefulWidget {
  const LocalModeApp({super.key, required this.onExit});
  final VoidCallback onExit;

  @override
  State<LocalModeApp> createState() => _LocalModeAppState();
}

class _LocalModeAppState extends State<LocalModeApp> {
  final store = GhStore(); // reuse the model endpoint + key
  bool _loading = true;

  final _task = TextEditingController();
  final List<LocalFile> _picked = [];
  bool _running = false;
  final _log = <String>[];
  LocalResult? _result;
  String _err = '';

  @override
  void initState() {
    super.initState();
    store.load().then((_) => setState(() => _loading = false));
  }

  @override
  void dispose() {
    _task.dispose();
    super.dispose();
  }

  Future<void> _pick() async {
    final res = await FilePicker.pickFiles(allowMultiple: true, withData: true);
    if (res == null) return;
    setState(() {
      for (final f in res.files) {
        if (f.bytes == null) continue;
        String text;
        try {
          text = utf8.decode(f.bytes!);
        } catch (_) {
          _err = '${f.name} is not a text file — skipped.';
          continue;
        }
        _picked.removeWhere((p) => p.name == f.name);
        _picked.add(LocalFile(f.name, text));
      }
    });
  }

  Future<void> _run() async {
    if (_picked.isEmpty || _task.text.trim().isEmpty) return;
    if (!store.configured && store.modelKey.isEmpty) {
      setState(() => _err = 'Set a model API key first (GitHub mode → setup).');
      return;
    }
    setState(() {
      _running = true;
      _log.clear();
      _result = null;
      _err = '';
    });
    final agent = LocalAgent(ModelClient(
      base: store.modelBase,
      apiKey: store.modelKey,
      model: store.model,
    ));
    try {
      final r = await agent.run(_picked, _task.text.trim(),
          log: (l) => setState(() => _log.add(l)));
      setState(() => _result = r);
    } catch (e) {
      setState(() => _err = '$e'.replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _running = false);
    }
  }

  Future<void> _save(LocalFile f) async {
    final path = await FilePicker.saveFile(
      fileName: f.name,
      bytes: utf8.encode(f.content),
    );
    if (path != null && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Saved ${f.name}')));
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Scaffold(body: Center(child: CircularProgressIndicator()));
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: widget.onExit),
        title: const Text('Files on this device'),
      ),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        if (store.modelKey.isEmpty)
          const Card(
            color: Color(0xFF2A1E1E),
            child: Padding(
              padding: EdgeInsets.all(12),
              child: Text('No model key yet. Go to the chooser → "Work on a GitHub repo" → '
                  'setup, add your NVIDIA key, come back.'),
            ),
          ),
        OutlinedButton.icon(
          onPressed: _running ? null : _pick,
          icon: const Icon(Icons.attach_file),
          label: Text(_picked.isEmpty ? 'Pick files' : 'Add / replace files'),
        ),
        for (final f in _picked)
          ListTile(
            dense: true,
            leading: const Icon(Icons.description_outlined, size: 20),
            title: Text(f.name),
            subtitle: Text('${f.content.length} chars'),
            trailing: IconButton(
              icon: const Icon(Icons.close, size: 18),
              onPressed: _running ? null : () => setState(() => _picked.remove(f)),
            ),
          ),
        const SizedBox(height: 8),
        TextField(
          controller: _task,
          maxLines: 4,
          enabled: !_running,
          decoration: const InputDecoration(
            labelText: 'What should change?',
            hintText: 'e.g. add docstrings to every function; fix the failing assertions',
          ),
        ),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: (_running || _picked.isEmpty) ? null : _run,
          icon: _running
              ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.auto_fix_high),
          label: Text(_running ? 'Working…' : 'Apply with AI'),
        ),
        const SizedBox(height: 12),
        for (final l in _log)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 2),
            child: Text('• $l', style: const TextStyle(color: Colors.white70, fontSize: 13)),
          ),
        if (_err.isNotEmpty) ...[
          const SizedBox(height: 12),
          Text(_err, style: const TextStyle(color: Colors.redAccent)),
        ],
        if (_result != null) ...[
          const SizedBox(height: 16),
          Text(_result!.summary, style: const TextStyle(color: Colors.white70)),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: () async {
              for (final f in _result!.changes) {
                await _save(f);
              }
            },
            icon: const Icon(Icons.save),
            label: Text('Save all ${_result!.changes.length} changed file(s)'),
          ),
          const SizedBox(height: 8),
          for (final f in _result!.changes)
            Card(
              color: const Color(0xFF171A21),
              child: ListTile(
                title: Text(f.name),
                subtitle: Text('${f.content.length} chars — tap to save individually'),
                trailing: const Icon(Icons.save_alt),
                onTap: () => _save(f),
              ),
            ),
        ],
      ]),
    );
  }
}
