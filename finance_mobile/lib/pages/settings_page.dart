import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../db/database.dart';
import '../services/api.dart';
import '../services/sync.dart';
import '../version.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  final _serverController = TextEditingController();
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _busy = false;
  String _status = '未登录';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final server = await LocalDb.meta('server_url') ?? '';
    final token = await LocalDb.meta('token') ?? '';
    if (!mounted) return;
    _serverController.text = server.isEmpty ? 'http://127.0.0.1:8766' : server;
    _status = token.isEmpty ? '未登录' : '已登录';
    setState(() {});
  }

  Future<void> _login() async {
    setState(() => _busy = true);
    try {
      final username = _usernameController.text.trim();
      final token = username.isEmpty
          ? await ApiClient.login(_serverController.text, _passwordController.text)
          : await ApiClient.loginUser(
              _serverController.text, username, _passwordController.text);
      await LocalDb.setMeta('server_url', _serverController.text.trim().replaceAll(RegExp(r'/$'), ''));
      await LocalDb.setMeta('token', token);
      _status = '已登录';
      _toast('登录成功');
    } catch (e) {
      _toast('登录失败：$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _register() async {
    setState(() => _busy = true);
    try {
      final username = _usernameController.text.trim();
      await ApiClient.registerUser(
        _serverController.text, username, _passwordController.text);
      final token = await ApiClient.loginUser(
        _serverController.text, username, _passwordController.text);
      await LocalDb.setMeta(
          'server_url', _serverController.text.trim().replaceAll(RegExp(r'/$'), ''));
      await LocalDb.setMeta('token', token);
      _status = '已登录';
      _toast('注册成功并已登录');
    } catch (e) {
      _toast('注册失败：$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<ApiClient?> _client() async {
    final server = await LocalDb.meta('server_url') ?? '';
    final token = await LocalDb.meta('token') ?? '';
    if (server.isEmpty || token.isEmpty) {
      _toast('请先登录');
      return null;
    }
    return ApiClient(baseUrl: server, token: token);
  }

  Future<void> _syncNow() async {
    final api = await _client();
    if (api == null) return;
    setState(() => _busy = true);
    try {
      await SyncService.fullSync(api);
      _status = '同步完成';
      _toast('同步完成');
    } catch (e) {
      _status = '同步失败';
      _toast('同步失败：$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _checkUpdate() async {
    final api = await _client();
    if (api == null) return;
    try {
      final info = await api.checkUpdate();
      if (!mounted) return;
      showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('版本更新'),
          content: Text(
            '服务端版本：${info['version']}\n'
            '${info['notes']}\n'
            'APK 地址：${info['apk_url'] ?? '未配置'}',
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context), child: const Text('知道了')),
          ],
        ),
      );
    } catch (e) {
      _toast('检查更新失败：$e');
    }
  }

  Future<void> _updateApp() async {
    final api = await _client();
    if (api == null) return;
    try {
      final info = await api.checkUpdate();
      final apkUrl = (info['apk_url'] as String? ?? '').trim();
      if (apkUrl.isEmpty) {
        _toast('服务端尚未配置 APK 下载地址');
        return;
      }
      final uri = Uri.parse(apkUrl);
      final ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
      _toast(ok ? '已打开下载，请安装 APK' : '无法打开下载地址');
    } catch (e) {
      _toast('更新失败：$e');
    }
  }

  Future<void> _logout() async {
    await LocalDb.setMeta('token', '');
    setState(() => _status = '未登录');
    _toast('已退出登录');
  }

  void _toast(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('设置')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
            controller: _serverController,
            decoration: const InputDecoration(
              labelText: '同步服务地址',
              hintText: '如 http://192.168.1.10:8766',
            ),
          ),
          TextField(
            controller: _usernameController,
            decoration: const InputDecoration(labelText: '用户名（可留空）'),
          ),
          TextField(
            controller: _passwordController,
            obscureText: true,
            decoration: const InputDecoration(labelText: '服务器密码'),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              FilledButton(onPressed: _busy ? null : _login, child: const Text('登录')),
              OutlinedButton(onPressed: _busy ? null : _register, child: const Text('注册')),
              OutlinedButton(onPressed: _busy ? null : _syncNow, child: const Text('立即同步')),
              OutlinedButton(onPressed: _busy ? null : _checkUpdate, child: const Text('检查更新')),
              FilledButton.tonal(
                  onPressed: _busy ? null : _updateApp, child: const Text('同步更新版本')),
              OutlinedButton(onPressed: _busy ? null : _logout, child: const Text('退出登录')),
            ],
          ),
          const SizedBox(height: 12),
          Text('状态：$_status', style: const TextStyle(fontSize: 14)),
          const SizedBox(height: 12),
          const Card(
            child: Padding(
              padding: EdgeInsets.all(12),
              child: Text('当前版本 V$appVersion\n一次登录长期有效，清除软件缓存或退出登录后需重新登录。'),
            ),
          ),
        ],
      ),
    );
  }
}
