// Smoke test: the app builds and shows the pairing screen when unpaired.
import 'package:flutter_test/flutter_test.dart';
import 'package:vajra_companion/main.dart';

void main() {
  testWidgets('shows the pairing screen on first launch', (WidgetTester tester) async {
    await tester.pumpWidget(const VajraApp());
    await tester.pump();
    expect(find.text('Pair with your PC'), findsOneWidget);
    expect(find.text('Connect'), findsOneWidget);
  });
}
