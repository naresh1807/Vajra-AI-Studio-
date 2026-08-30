import 'dart:convert';

import 'package:http/http.dart' as http;

/// OpenAI-compatible chat client (NVIDIA NIM by default). Non-streaming.
class ModelClient {
  ModelClient({required this.base, required this.apiKey, required this.model});
  final String base;
  final String apiKey;
  final String model;

  Future<String> chat(List<Map<String, String>> messages,
      {double temperature = 0.1, int maxTokens = 4000}) async {
    final r = await http.post(
      Uri.parse('$base/chat/completions'),
      headers: {
        'Authorization': 'Bearer $apiKey',
        'Content-Type': 'application/json',
      },
      body: jsonEncode({
        'model': model,
        'messages': messages,
        'temperature': temperature,
        'max_tokens': maxTokens,
      }),
    );
    if (r.statusCode >= 400) {
      String msg = r.body;
      try {
        msg = (jsonDecode(r.body) as Map)['error']?['message']?.toString() ?? r.body;
      } catch (_) {}
      throw Exception('Model ${r.statusCode}: $msg');
    }
    final m = jsonDecode(r.body) as Map<String, dynamic>;
    final choices = m['choices'] as List;
    if (choices.isEmpty) throw Exception('Model returned no choices');
    return ((choices.first as Map)['message'] as Map)['content'] as String? ?? '';
  }
}

/// Pull the first fenced ```json ... ``` block (or the first bare {...}/[...]).
dynamic extractJson(String text) {
  final fence = RegExp(r'```(?:json)?\s*([\s\S]*?)```').firstMatch(text);
  final body = fence != null ? fence.group(1)! : text;
  final start = body.indexOf(RegExp(r'[\[{]'));
  if (start < 0) throw Exception('no JSON found in the model reply');
  // walk to the matching close
  var depth = 0;
  var inStr = false;
  var esc = false;
  for (var i = start; i < body.length; i++) {
    final c = body[i];
    if (inStr) {
      if (esc) {
        esc = false;
      } else if (c == r'\') {
        esc = true;
      } else if (c == '"') {
        inStr = false;
      }
      continue;
    }
    if (c == '"') {
      inStr = true;
    } else if (c == '{' || c == '[') {
      depth++;
    } else if (c == '}' || c == ']') {
      depth--;
      if (depth == 0) return jsonDecode(body.substring(start, i + 1));
    }
  }
  throw Exception('unterminated JSON in the model reply');
}
