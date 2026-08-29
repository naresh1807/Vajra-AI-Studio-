import 'dart:async';
import 'package:flutter/material.dart';
import 'api.dart';

void main() => runApp(const VajraApp());

const _bg = Color(0xFF0F1115);
const _panel = Color(0xFF171A21);
const _accent = Color(0xFF6EA8FE);

class VajraApp extends StatelessWidget {
  const VajraApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'Vajra Mobile',
        theme: ThemeData(
          brightness: Brightness.dark,
          scaffoldBackgroundColor: _bg,
          colorScheme: const ColorScheme.dark(primary: _accent, surface: _panel),
          useMaterial3: true,
        ),
        home: const Home(),
      );
}

class Home extends StatefulWidget {
  const Home({super.key});
  @override
  State<Home> createState() => _HomeState();
}

class _RunRef {
  _RunRef(this.kind, this.id, this.label);
  final String kind, id, label;
  Map<String, dynamic> state = {};
}

class _HomeState extends State<Home> {
  final api = VajraApi();
  bool paired = false;
  int tab = 0;
  final urlC = TextEditingController();
  final tokC = TextEditingController();
  final cmpC = TextEditingController();
  final goalC = TextEditingController();
  List<dynamic> projects = [];
  String? proj;
  final List<_RunRef> runs = [];
  List<dynamic> approvals = [];
  Timer? _poll;

  @override
  void initState() {
    super.initState();
    api.load().then((_) {
      urlC.text = api.baseUrl;
      tokC.text = api.token;
      if (api.baseUrl.isNotEmpty && api.token.isNotEmpty) _pair();
    });
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _pair() async {
    await api.save(urlC.text, tokC.text);
    if (!await api.ping()) {
      _snack('Could not connect / bad token');
      return;
    }
    setState(() => paired = true);
    projects = await api.projects().catchError((_) => []);
    _poll = Timer.periodic(const Duration(seconds: 2), (_) => _tick());
  }

  Future<void> _tick() async {
    try {
      approvals = await api.approvals();
      for (final r in runs) {
        r.state = r.kind == 'computer' ? await api.computerRun(r.id) : await api.agentRun(r.id);
      }
      if (mounted) setState(() {});
    } catch (_) {}
  }

  void _snack(String m) => ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(m)));

  Future<void> _runComputer() async {
    final t = cmpC.text.trim();
    if (t.isEmpty) return;
    cmpC.clear();
    final r = await api.runComputer(t);
    setState(() {
      runs.insert(0, _RunRef('computer', r['id'], t));
      tab = 1;
    });
  }

  Future<void> _runAgent() async {
    final t = goalC.text.trim();
    if (proj == null || t.isEmpty) {
      _snack('Pick a project and enter a goal');
      return;
    }
    goalC.clear();
    final r = await api.runAgent(t, proj!);
    setState(() {
      runs.insert(0, _RunRef('agent', r['id'], t));
      tab = 1;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!paired) return _pairScreen();
    return Scaffold(
      appBar: AppBar(title: const Text('VAJRA Mobile')),
      body: [_newTab(), _tasksTab(), _approvalsTab()][tab],
      bottomNavigationBar: NavigationBar(
        selectedIndex: tab,
        onDestinationSelected: (i) => setState(() => tab = i),
        destinations: [
          const NavigationDestination(icon: Icon(Icons.add), label: 'New'),
          const NavigationDestination(icon: Icon(Icons.list), label: 'Tasks'),
          NavigationDestination(
            icon: Badge(label: Text('${approvals.length}'), isLabelVisible: approvals.isNotEmpty, child: const Icon(Icons.verified_user)),
            label: 'Approvals',
          ),
        ],
      ),
    );
  }

  Widget _pairScreen() => Scaffold(
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
              const Text('Pair with your PC', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
              const SizedBox(height: 16),
              TextField(controller: urlC, decoration: const InputDecoration(hintText: 'http://192.168.1.20:8760')),
              const SizedBox(height: 10),
              TextField(controller: tokC, decoration: const InputDecoration(hintText: 'pairing token')),
              const SizedBox(height: 16),
              FilledButton(onPressed: _pair, child: const Text('Connect')),
            ]),
          ),
        ),
      );

  Widget _newTab() => ListView(padding: const EdgeInsets.all(16), children: [
        _card('Computer task', [
          const Text('Acts on the PC outside any project.', style: TextStyle(color: Colors.white60)),
          TextField(controller: cmpC, maxLines: 3, decoration: const InputDecoration(hintText: "create a folder 'notes' on the Desktop")),
          FilledButton(onPressed: _runComputer, child: const Text('Run')),
        ]),
        _card('Project task', [
          DropdownButton<String>(
            isExpanded: true,
            value: proj,
            hint: const Text('pick a project'),
            items: projects.map((p) => DropdownMenuItem(value: p['root_path'] as String, child: Text(p['name'] as String))).toList(),
            onChanged: (v) => setState(() => proj = v),
          ),
          TextField(controller: goalC, maxLines: 3, decoration: const InputDecoration(hintText: 'add a /health endpoint and a test')),
          FilledButton(onPressed: _runAgent, child: const Text('Run')),
        ]),
      ]);

  Widget _tasksTab() {
    if (runs.isEmpty) return const Center(child: Text('No tasks yet.'));
    return ListView(padding: const EdgeInsets.all(16), children: [
      for (final r in runs)
        _card(r.kind, [
          Text(r.label),
          if (r.state['status'] != null) Chip(label: Text(r.state['status'] as String)),
          if (r.state['reply'] != null) Text(r.state['reply'] as String, style: const TextStyle(color: Colors.white60)),
          for (final t in (r.state['tasks'] as List? ?? []))
            Text("• ${t['title']}  [${t['state']}]", style: const TextStyle(color: Colors.white60, fontSize: 13)),
          if (r.kind == 'agent' && !['passed', 'failed'].contains(r.state['status']))
            OutlinedButton(onPressed: () => api.stopAgent(r.id), child: const Text('Stop')),
        ]),
    ]);
  }

  Widget _approvalsTab() {
    if (approvals.isEmpty) return const Center(child: Text('Nothing waiting.'));
    return ListView(padding: const EdgeInsets.all(16), children: [
      for (final a in approvals)
        _card(a['tool_name'] as String, [
          Text(a['reason']?.toString() ?? '', style: const TextStyle(color: Colors.white60)),
          Text('${a['arguments']}', style: const TextStyle(color: Colors.white38, fontSize: 12)),
          Row(children: [
            Expanded(child: FilledButton(onPressed: () => _approve(a['id'] as String, 'approved'), child: const Text('Approve'))),
            const SizedBox(width: 8),
            Expanded(child: OutlinedButton(onPressed: () => _approve(a['id'] as String, 'rejected'), child: const Text('Reject'))),
          ]),
        ]),
    ]);
  }

  Future<void> _approve(String id, String verdict) async {
    await api.resolveApproval(id, verdict);
    _tick();
  }

  Widget _card(String title, List<Widget> children) => Card(
        color: _panel,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              ...children,
            ],
          ),
        ),
      );
}
