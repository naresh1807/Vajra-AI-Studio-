// Smoke test: the app builds and shows the login screen when not connected.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vajra_companion/api.dart';
import 'package:vajra_companion/main.dart';

void main() {
  testWidgets('shows the login screen on first launch', (WidgetTester tester) async {
    await tester.pumpWidget(const VajraApp());
    await tester.pump();
    expect(find.text('Log in to your PC'), findsOneWidget);
    expect(find.text('Log in'), findsOneWidget);
    expect(find.widgetWithText(TextField, 'Vajra password'), findsOneWidget);
  });

  test('normalizeUrl adds a scheme and trims trailing slashes', () {
    expect(VajraApi.normalizeUrl('192.168.0.105:8760'), 'http://192.168.0.105:8760');
    expect(VajraApi.normalizeUrl('http://x:8760/'), 'http://x:8760');
    expect(VajraApi.normalizeUrl('  https://x  '), 'https://x');
    expect(VajraApi.normalizeUrl(''), '');
  });
}
