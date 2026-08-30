import 'dart:convert';

import 'package:http/http.dart' as http;

/// Minimal GitHub REST v3 client - just what standalone mode needs:
/// list repos, read a tree + files, create a branch, write files, open a PR.
class GhApi {
  GhApi(this.token);
  final String token;
  static const _base = 'https://api.github.com';

  Map<String, String> get _h => {
        'Authorization': 'Bearer $token',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
      };

  Never _fail(http.Response r) {
    String msg = r.body;
    try {
      msg = (jsonDecode(r.body) as Map)['message']?.toString() ?? r.body;
    } catch (_) {}
    throw Exception('GitHub ${r.statusCode}: $msg');
  }

  Future<Map<String, dynamic>> _get(String path) async {
    final r = await http.get(Uri.parse('$_base$path'), headers: _h);
    if (r.statusCode >= 400) _fail(r);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> _getList(String path) async {
    final r = await http.get(Uri.parse('$_base$path'), headers: _h);
    if (r.statusCode >= 400) _fail(r);
    return jsonDecode(r.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> _post(String path, Object body) async {
    final r = await http.post(Uri.parse('$_base$path'),
        headers: {..._h, 'Content-Type': 'application/json'}, body: jsonEncode(body));
    if (r.statusCode >= 400) _fail(r);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> _put(String path, Object body) async {
    final r = await http.put(Uri.parse('$_base$path'),
        headers: {..._h, 'Content-Type': 'application/json'}, body: jsonEncode(body));
    if (r.statusCode >= 400) _fail(r);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  /// The authenticated user's login (also validates the token).
  Future<String> me() async => (await _get('/user'))['login'] as String;

  /// Repos the token can push to, most-recently-pushed first.
  Future<List<Repo>> repos() async {
    final out = <Repo>[];
    for (var page = 1; page <= 4; page++) {
      final list = await _getList('/user/repos?per_page=100&sort=pushed&affiliation=owner,collaborator&page=$page');
      for (final r in list) {
        final m = r as Map<String, dynamic>;
        if (m['permissions']?['push'] == true) {
          out.add(Repo(m['full_name'] as String, m['default_branch'] as String? ?? 'main',
              (m['private'] as bool?) ?? false));
        }
      }
      if (list.length < 100) break;
    }
    return out;
  }

  Future<List<String>> branches(String fullName) async {
    final list = await _getList('/repos/$fullName/branches?per_page=100');
    return [for (final b in list) (b as Map)['name'] as String];
  }

  /// HEAD commit sha of a branch.
  Future<String> headSha(String fullName, String branch) async {
    final m = await _get('/repos/$fullName/git/ref/heads/$branch');
    return (m['object'] as Map)['sha'] as String;
  }

  /// Recursive path list of a branch (files only), capped.
  Future<List<String>> tree(String fullName, String branch) async {
    final m = await _get('/repos/$fullName/git/trees/$branch?recursive=1');
    final entries = (m['tree'] as List).cast<Map<String, dynamic>>();
    return [
      for (final e in entries)
        if (e['type'] == 'blob' && (e['size'] as int? ?? 0) < 200000) e['path'] as String,
    ];
  }

  /// File text + its blob sha (needed to update it). Returns null if absent.
  Future<GhFile?> file(String fullName, String path, String ref) async {
    final r = await http.get(
      Uri.parse('$_base/repos/$fullName/contents/${Uri.encodeFull(path)}?ref=$ref'),
      headers: _h,
    );
    if (r.statusCode == 404) return null;
    if (r.statusCode >= 400) _fail(r);
    final m = jsonDecode(r.body) as Map<String, dynamic>;
    final b64 = (m['content'] as String).replaceAll('\n', '');
    return GhFile(path, utf8.decode(base64.decode(b64)), m['sha'] as String);
  }

  Future<void> createBranch(String fullName, String newBranch, String fromSha) async {
    await _post('/repos/$fullName/git/refs', {'ref': 'refs/heads/$newBranch', 'sha': fromSha});
  }

  /// Create or update one file on a branch. [sha] is the existing blob sha (omit for new files).
  Future<void> putFile(String fullName, String path, String content, String message,
      String branch, String? sha) async {
    final body = <String, dynamic>{
      'message': message,
      'content': base64.encode(utf8.encode(content)),
      'branch': branch,
    };
    if (sha != null) body['sha'] = sha;
    await _put('/repos/$fullName/contents/${Uri.encodeFull(path)}', body);
  }

  /// Open a PR, returns its html_url.
  Future<String> openPr(String fullName, String head, String base, String title, String body) async {
    final m = await _post('/repos/$fullName/pulls',
        {'title': title, 'head': head, 'base': base, 'body': body});
    return m['html_url'] as String;
  }
}

class Repo {
  Repo(this.fullName, this.defaultBranch, this.private);
  final String fullName;
  final String defaultBranch;
  final bool private;
}

class GhFile {
  GhFile(this.path, this.content, this.sha);
  final String path;
  final String content;
  final String sha;
}
