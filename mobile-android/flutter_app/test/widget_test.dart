// Smoke test: the app builds and shows the pairing screen when unpaired,
// with both pairing modes (PIN / Token) offered.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vajra_companion/main.dart';

void main() {
  testWidgets('shows the pairing screen on first launch', (WidgetTester tester) async {
    await tester.pumpWidget(const VajraApp());
    await tester.pump();
    expect(find.text('Pair with your PC'), findsOneWidget);
    expect(find.text('Connect'), findsOneWidget);
    expect(find.text('PIN'), findsOneWidget);
    expect(find.text('Token'), findsOneWidget);
    // default mode is PIN: the 6-digit field and its hint are visible
    expect(find.text('6-digit code'), findsOneWidget);
  });

  testWidgets('switching to Token mode swaps the input', (WidgetTester tester) async {
    await tester.pumpWidget(const VajraApp());
    await tester.pump();
    await tester.tap(find.text('Token'));
    await tester.pump();
    expect(find.text('6-digit code'), findsNothing);
    expect(find.text('device secret / paired token'), findsOneWidget);
  });
}
