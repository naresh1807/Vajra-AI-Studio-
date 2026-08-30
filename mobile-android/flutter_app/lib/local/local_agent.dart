import '../github/nim.dart';

class LocalFile {
  LocalFile(this.name, this.content);
  final String name;
  String content;
}

class LocalResult {
  LocalResult(this.summary, this.changes);
  final String summary;
  final List<LocalFile> changes;
}

/// Edit files the user picked from device storage / Drive / a USB drive.
/// One model round-trip: picked files + task -> full new contents.
class LocalAgent {
  LocalAgent(this.model);
  final ModelClient model;

  static const _maxFileChars = 20000;

  Future<LocalResult> run(List<LocalFile> files, String task,
      {void Function(String)? log}) async {
    log?.call('Sending ${files.length} file(s) to the model…');
    final ctx = StringBuffer();
    for (final f in files) {
      final body = f.content.length > _maxFileChars
          ? '${f.content.substring(0, _maxFileChars)}\n… (truncated)'
          : f.content;
      ctx
        ..writeln('=== FILE: ${f.name} ===')
        ..writeln(body)
        ..writeln();
    }

    final reply = await model.chat([
      {
        'role': 'system',
        'content': '''You edit the user's files. Return ONLY JSON, no prose:
{
  "summary": "what you changed and why, one paragraph",
  "changes": [ { "name": "<one of the given file names>", "content": "FULL new file content" } ]
}
Include the COMPLETE new content of every file you change. Only change files that need it.
Keep edits minimal and correct; match the existing style.''',
      },
      {'role': 'user', 'content': 'Task: $task\n\nFiles:\n\n$ctx'},
    ], maxTokens: 8000);

    log?.call('Parsing the reply…');
    final obj = extractJson(reply);
    if (obj is! Map) throw Exception('model did not return a JSON object');
    final names = {for (final f in files) f.name};
    final changes = <LocalFile>[];
    for (final c in (obj['changes'] as List? ?? [])) {
      final m = c as Map;
      final name = m['name']?.toString() ?? '';
      if (names.contains(name) && m['content'] is String) {
        changes.add(LocalFile(name, m['content'] as String));
      }
    }
    if (changes.isEmpty) throw Exception('the model proposed no changes to the given files');
    return LocalResult(obj['summary']?.toString() ?? task, changes);
  }
}
