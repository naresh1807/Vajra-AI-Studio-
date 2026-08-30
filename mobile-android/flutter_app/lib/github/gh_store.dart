import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Credentials + settings for standalone GitHub mode. The GitHub token and the
/// model API key live in the platform keystore (flutter_secure_storage); they
/// never leave the phone except in the Authorization header to github.com /
/// the model endpoint you configure.
class GhStore {
  static const _s = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

  static const _kGh = 'gh.token';
  static const _kModelKey = 'gh.model_key';
  static const _kModelBase = 'gh.model_base';
  static const _kModel = 'gh.model';

  static const defaultBase = 'https://integrate.api.nvidia.com/v1';
  static const defaultModel = 'nvidia/nemotron-3-super-120b-a12b';

  String ghToken = '';
  String modelKey = '';
  String modelBase = defaultBase;
  String model = defaultModel;

  Future<void> load() async {
    ghToken = await _s.read(key: _kGh) ?? '';
    modelKey = await _s.read(key: _kModelKey) ?? '';
    modelBase = await _s.read(key: _kModelBase) ?? defaultBase;
    model = await _s.read(key: _kModel) ?? defaultModel;
  }

  Future<void> save({
    required String ghToken,
    required String modelKey,
    required String modelBase,
    required String model,
  }) async {
    this.ghToken = ghToken.trim();
    this.modelKey = modelKey.trim();
    this.modelBase = modelBase.trim().replaceAll(RegExp(r'/+$'), '');
    this.model = model.trim();
    await _s.write(key: _kGh, value: this.ghToken);
    await _s.write(key: _kModelKey, value: this.modelKey);
    await _s.write(key: _kModelBase, value: this.modelBase);
    await _s.write(key: _kModel, value: this.model);
  }

  bool get configured => ghToken.isNotEmpty && modelKey.isNotEmpty;

  Future<void> clear() async {
    await _s.deleteAll();
    ghToken = '';
    modelKey = '';
    modelBase = defaultBase;
    model = defaultModel;
  }
}
