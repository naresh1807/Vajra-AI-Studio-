import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:vajra_companion/api.dart';
import 'package:vajra_companion/github/nim.dart';
import 'package:vajra_companion/main.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets('first launch shows the mode chooser', (tester) async {
    await tester.pumpWidget(const VajraApp());
    await tester.pumpAndSettle();
    expect(find.text('Work on a GitHub repo'), findsOneWidget);
    expect(find.text('Control my PC'), findsOneWidget);
  });

  testWidgets('choosing "Control my PC" shows the login screen', (tester) async {
    await tester.pumpWidget(const VajraApp());
    await tester.pumpAndSettle();
    await tester.tap(find.text('Control my PC'));
    await tester.pumpAndSettle();
    expect(find.text('Log in to your PC'), findsOneWidget);
    expect(find.widgetWithText(TextField, 'Vajra password'), findsOneWidget);
  });

  test('normalizeUrl adds a scheme and trims trailing slashes', () {
    expect(VajraApi.normalizeUrl('192.168.0.105:8760'), 'http://192.168.0.105:8760');
    expect(VajraApi.normalizeUrl('http://x:8760/'), 'http://x:8760');
    expect(VajraApi.normalizeUrl('  https://x  '), 'https://x');
    expect(VajraApi.normalizeUrl(''), '');
  });

  test('extractJson pulls a fenced object out of a chatty reply', () {
    final o = extractJson('sure!\n```json\n{"a": 1, "b": [2, 3]}\n```\nhope that helps');
    expect((o as Map)['a'], 1);
    expect(o['b'], [2, 3]);
  });

  test('extractJson handles braces inside strings', () {
    final o = extractJson('{"msg": "a } b { c", "n": 2}');
    expect((o as Map)['msg'], 'a } b { c');
    expect(o['n'], 2);
  });
}
