import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import 'gh_agent.dart';
import 'gh_api.dart';
import 'gh_store.dart';
import 'nim.dart';

/// Standalone GitHub mode: no PC, no LAN. Configure a GitHub token + a model
/// key once, pick a repo, describe a task, get a pull request.
class GhModeApp extends StatefulWidget {
  const GhModeApp({super.key, required this.onExit});
  final VoidCallback onExit;

  @override
  State<GhModeApp> createState() => _GhModeAppState();
}

class _GhModeAppState extends State<GhModeApp> {
  final store = GhStore();
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    store.load().then((_) => setState(() => _loading = false));
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Scaffold(body: Center(child: CircularProgressIndicator()));
    if (!store.configured) {
      return GhSetupScreen(
        store: store,
        onExit: widget.onExit,
        onDone: () => setState(() {}),
      );
    }
    return GhRepoScreen(
      store: store,
      onExit: widget.onExit,
      onSettings: () async {
        await Navigator.push(context, MaterialPageRoute(
          builder: (_) => GhSetupScreen(store: store, onExit: widget.onExit, onDone: () {}),
        ));
        setState(() {});
      },
    );
  }
}

class GhSetupScreen extends StatefulWidget {
  const GhSetupScreen({super.key, required this.store, required this.onDone, required this.onExit});
  final GhStore store;
  final VoidCallback onDone;
  final VoidCallback onExit;

  @override
  State<GhSetupScreen> createState() => _GhSetupScreenState();
}

class _GhSetupScreenState extends State<GhSetupScreen> {
  late final _gh = TextEditingController(text: widget.store.ghToken);
  late final _key = TextEditingController(text: widget.store.modelKey);
  late final _base = TextEditingController(text: widget.store.modelBase);
  late final _model = TextEditingController(text: widget.store.model);
  bool _busy = false;
  String _err = '';

  @override
  void dispose() {
    _gh.dispose();
    _key.dispose();
    _base.dispose();
    _model.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() {
      _busy = true;
      _err = '';
    });
    try {
      final login = await GhApi(_gh.text.trim()).me();
      await widget.store.save(
        ghToken: _gh.text,
        modelKey: _key.text,
        modelBase: _base.text.isEmpty ? GhStore.defaultBase : _base.text,
        model: _model.text.isEmpty ? GhStore.defaultModel : _model.text,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('GitHub: signed in as $login')));
      Navigator.of(context).canPop() ? Navigator.pop(context) : widget.onDone();
    } catch (e) {
      setState(() => _err = '$e'.replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('GitHub mode — setup'),
        actions: [TextButton(onPressed: widget.onExit, child: const Text('PC mode'))],
      ),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        const Text('Works without a PC. Your tokens stay in the phone keystore.',
            style: TextStyle(color: Colors.white60)),
        const SizedBox(height: 16),
        TextField(
          controller: _gh,
          obscureText: true,
          decoration: const InputDecoration(
            labelText: 'GitHub token',
            helperText: 'github.com → Settings → Developer settings → Personal access token → repo scope',
            helperMaxLines: 3,
          ),
        ),
        const SizedBox(height: 16),
        TextField(
          controller: _key,
          obscureText: true,
          decoration: const InputDecoration(
            labelText: 'Model API key',
            helperText: 'NVIDIA NIM key (nvapi-…) from build.nvidia.com',
            helperMaxLines: 2,
          ),
        ),
        const SizedBox(height: 16),
        TextField(controller: _base, decoration: const InputDecoration(labelText: 'Model endpoint')),
        const SizedBox(height: 12),
        TextField(controller: _model, decoration: const InputDecoration(labelText: 'Model')),
        const SizedBox(height: 20),
        FilledButton(
          onPressed: _busy ? null : _save,
          child: Text(_busy ? 'Checking…' : 'Save & verify'),
        ),
        if (_err.isNotEmpty) ...[
          const SizedBox(height: 12),
          Text(_err, style: const TextStyle(color: Colors.redAccent)),
        ],
        if (widget.store.configured) ...[
          const SizedBox(height: 24),
          TextButton(
            onPressed: () async {
              await widget.store.clear();
              if (mounted) setState(() {});
            },
            child: const Text('Sign out / clear tokens'),
          ),
        ],
      ]),
    );
  }
}

class GhRepoScreen extends StatefulWidget {
  const GhRepoScreen({super.key, required this.store, required this.onSettings, required this.onExit});
  final GhStore store;
  final VoidCallback onSettings;
  final VoidCallback onExit;

  @override
  State<GhRepoScreen> createState() => _GhRepoScreenState();
}

class _GhRepoScreenState extends State<GhRepoScreen> {
  List<Repo>? _repos;
  String _err = '';

  GhApi get _api => GhApi(widget.store.ghToken);

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _repos = null;
      _err = '';
    });
    try {
      final r = await _api.repos();
      setState(() => _repos = r);
    } catch (e) {
      setState(() => _err = '$e'.replaceFirst('Exception: ', ''));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Pick a repository'),
        actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
          IconButton(onPressed: widget.onSettings, icon: const Icon(Icons.settings)),
          TextButton(onPressed: widget.onExit, child: const Text('PC mode')),
        ],
      ),
      body: _err.isNotEmpty
          ? Center(child: Padding(padding: const EdgeInsets.all(24), child: Text(_err, style: const TextStyle(color: Colors.redAccent))))
          : _repos == null
              ? const Center(child: CircularProgressIndicator())
              : ListView(
                  children: [
                    for (final r in _repos!)
                      ListTile(
                        leading: Icon(r.private ? Icons.lock_outline : Icons.folder_outlined),
                        title: Text(r.fullName),
                        subtitle: Text('default: ${r.defaultBranch}'),
                        onTap: () => Navigator.push(context, MaterialPageRoute(
                          builder: (_) => GhTaskScreen(store: widget.store, repo: r),
                        )),
                      ),
                  ],
                ),
    );
  }
}

class GhTaskScreen extends StatefulWidget {
  const GhTaskScreen({super.key, required this.store, required this.repo});
  final GhStore store;
  final Repo repo;

  @override
  State<GhTaskScreen> createState() => _GhTaskScreenState();
}

class _GhTaskScreenState extends State<GhTaskScreen> {
  final _task = TextEditingController();
  List<String> _branches = [];
  String _base = '';
  bool _running = false;
  final _log = <String>[];
  PrResult? _result;
  String _err = '';

  @override
  void initState() {
    super.initState();
    _base = widget.repo.defaultBranch;
    GhApi(widget.store.ghToken).branches(widget.repo.fullName).then((b) {
      if (mounted) setState(() => _branches = b);
    }).catchError((_) {});
  }

  @override
  void dispose() {
    _task.dispose();
    super.dispose();
  }

  Future<void> _run() async {
    if (_task.text.trim().isEmpty) return;
    setState(() {
      _running = true;
      _log.clear();
      _result = null;
      _err = '';
    });
    final agent = GhAgent(
      GhApi(widget.store.ghToken),
      ModelClient(base: widget.store.modelBase, apiKey: widget.store.modelKey, model: widget.store.model),
    );
    try {
      final r = await agent.run(
        fullName: widget.repo.fullName,
        baseBranch: _base,
        task: _task.text.trim(),
        log: (l) => setState(() => _log.add(l)),
      );
      setState(() => _result = r);
    } catch (e) {
      setState(() => _err = '$e'.replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _running = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.repo.fullName)),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        Row(children: [
          const Text('Base branch  '),
          Expanded(
            child: DropdownButton<String>(
              isExpanded: true,
              value: _branches.contains(_base) ? _base : null,
              hint: Text(_base),
              items: [for (final b in _branches) DropdownMenuItem(value: b, child: Text(b))],
              onChanged: _running ? null : (v) => setState(() => _base = v ?? _base),
            ),
          ),
        ]),
        const SizedBox(height: 8),
        TextField(
          controller: _task,
          maxLines: 4,
          enabled: !_running,
          decoration: const InputDecoration(
            labelText: 'What should change?',
            hintText: 'e.g. add a /health endpoint returning {"ok": true} and a test for it',
          ),
        ),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: _running ? null : _run,
          icon: _running
              ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.rocket_launch),
          label: Text(_running ? 'Working…' : 'Create pull request'),
        ),
        const SizedBox(height: 16),
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
          Card(
            color: const Color(0xFF171A21),
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('Pull request opened', style: TextStyle(fontWeight: FontWeight.bold)),
                const SizedBox(height: 6),
                Text(_result!.summary, style: const TextStyle(color: Colors.white70)),
                const SizedBox(height: 6),
                Text('branch ${_result!.branch}  ·  ${_result!.files.length} file(s)',
                    style: const TextStyle(color: Colors.white38, fontSize: 12)),
                const SizedBox(height: 10),
                FilledButton.icon(
                  onPressed: () => launchUrl(Uri.parse(_result!.url), mode: LaunchMode.externalApplication),
                  icon: const Icon(Icons.open_in_new),
                  label: const Text('Review on GitHub'),
                ),
              ]),
            ),
          ),
        ],
      ]),
    );
  }
}
