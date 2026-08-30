import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

/// Thin client for the Vajra Local API (/api/*), same routes the desktop and
/// VS Code clients use. All calls carry the pairing token.
class VajraApi {
  String baseUrl = '';
  String token = '';

  Future<void> load() async {
    final p = await SharedPreferences.getInstance();
    baseUrl = p.getString('vajra.url') ?? '';
    token = p.getString('vajra.token') ?? '';
  }

  Future<void> save(String url, String tok) async {
    baseUrl = url.replaceAll(RegExp(r'/+$'), '');
    token = tok.trim();
    final p = await SharedPreferences.getInstance();
    await p.setString('vajra.url', baseUrl);
    await p.setString('vajra.token', token);
  }

  Map<String, String> get _h => {
        'X-Vajra-Token': token,
        'Content-Type': 'application/json',
      };

  Future<Map<String, dynamic>> _get(String path) async {
    final r = await http.get(Uri.parse('$baseUrl$path'), headers: _h);
    if (r.statusCode >= 400) throw Exception('${r.statusCode} ${r.body}');
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<dynamic> _getRaw(String path) async {
    final r = await http.get(Uri.parse('$baseUrl$path'), headers: _h);
    if (r.statusCode >= 400) throw Exception('${r.statusCode} ${r.body}');
    return jsonDecode(r.body);
  }

  Future<Map<String, dynamic>> _post(String path, Map<String, dynamic> body) async {
    final r = await http.post(Uri.parse('$baseUrl$path'), headers: _h, body: jsonEncode(body));
    if (r.statusCode >= 400) throw Exception('${r.statusCode} ${r.body}');
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> health() =>
      http.get(Uri.parse('$baseUrl/api/health')).then((r) => jsonDecode(r.body) as Map<String, dynamic>);

  /// PIN pairing: the desktop shows a 6-digit code (Vajra: Pair a Phone), the
  /// phone redeems it here — unauthenticated — for its own per-device token,
  /// which is then persisted. No shared secret is ever typed on the phone.
  Future<void> redeemPin(String url, String pin, String name) async {
    final base = url.replaceAll(RegExp(r'/+$'), '');
    final r = await http.post(
      Uri.parse('$base/api/pairing/redeem'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'pin': pin.trim(), 'name': name}),
    );
    if (r.statusCode >= 400) throw Exception('pairing failed: ${r.statusCode} ${r.body}');
    final tok = (jsonDecode(r.body) as Map<String, dynamic>)['token'] as String;
    await save(base, tok);
  }

  Future<bool> ping() async {
    try {
      await _get('/api/ping');
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<List<dynamic>> projects() => _getRaw('/api/projects').then((v) => v as List<dynamic>);

  Future<Map<String, dynamic>> runComputer(String instruction) =>
      _post('/api/computer/run', {'instruction': instruction});
  Future<Map<String, dynamic>> computerRun(String id) => _get('/api/computer/runs/$id');

  Future<Map<String, dynamic>> runAgent(String goal, String workspaceRoot) =>
      _post('/api/agent/run', {'goal': goal, 'workspace_root': workspaceRoot});
  Future<Map<String, dynamic>> agentRun(String id) => _get('/api/agent/runs/$id');
  Future<void> stopAgent(String id) => _post('/api/agent/stop', {'run_id': id});

  Future<List<dynamic>> approvals() => _getRaw('/api/approvals').then((v) => v as List<dynamic>);
  Future<void> resolveApproval(String id, String verdict) =>
      _post('/api/approvals', {'approval_id': id, 'verdict': verdict});
}
