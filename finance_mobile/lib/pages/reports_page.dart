import 'dart:convert';

import 'package:flutter/material.dart';

import '../db/database.dart';
import '../services/api.dart';

class ReportsPage extends StatefulWidget {
  const ReportsPage({super.key});

  @override
  State<ReportsPage> createState() => _ReportsPageState();
}

class _ReportsPageState extends State<ReportsPage> {
  final _periodController = TextEditingController(text: '2026 年');
  String _reportType = 'year';
  List<Map<String, Object?>> _reports = [];
  String _content = '';
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final reports = await LocalDb.entities('ai_reports');
    if (!mounted) return;
    setState(() => _reports = reports);
  }

  Future<ApiClient?> _client() async {
    final baseUrl = await LocalDb.meta('server_url') ?? '';
    final token = await LocalDb.meta('token') ?? '';
    if (baseUrl.isEmpty || token.isEmpty) return null;
    return ApiClient(baseUrl: baseUrl, token: token);
  }

  Future<void> _generate() async {
    final api = await _client();
    if (api == null) {
      _toast('请先在设置中登录同步服务');
      return;
    }
    setState(() => _busy = true);
    try {
      final result = await api.generateReport(_reportType, _periodController.text.trim());
      final content = result['content'] as String? ?? '';
      final now = DateTime.now().millisecondsSinceEpoch.toDouble();
      await LocalDb.upsertEntity(
        'ai_reports',
        now.toInt(),
        {
          'report_type': _reportType,
          'period_label': _periodController.text.trim(),
          'content': content,
          'model': result['model'] ?? '',
        },
        updatedAt: now,
      );
      setState(() => _content = content);
      await _load();
    } catch (e) {
      _toast('生成失败：$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _toast(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('智能报告'), actions: [
        IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
      ]),
      body: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          DropdownButtonFormField<String>(
            initialValue: _reportType,
            items: const [
              DropdownMenuItem(value: 'year', child: Text('年度报告')),
              DropdownMenuItem(value: 'month', child: Text('月度报告')),
              DropdownMenuItem(value: 'holding', child: Text('持仓分析')),
              DropdownMenuItem(value: 'custom', child: Text('自定义')),
            ],
            onChanged: (v) => setState(() => _reportType = v ?? 'year'),
          ),
          TextField(
            controller: _periodController,
            decoration: const InputDecoration(labelText: '报告期间'),
          ),
          FilledButton(
            onPressed: _busy ? null : _generate,
            child: Text(_busy ? '生成中…' : '生成报告'),
          ),
          if (_content.isNotEmpty)
            Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: SelectableText(_content),
              ),
            ),
          const SizedBox(height: 8),
          const Text('历史报告', style: TextStyle(fontWeight: FontWeight.bold)),
          for (final row in _reports) _reportCard(row),
        ],
      ),
    );
  }

  Widget _reportCard(Map<String, Object?> row) {
    final data = jsonDecode(row['data_json'] as String) as Map<String, dynamic>;
    return Card(
      child: ListTile(
        title: Text(data['period_label'] as String? ?? '报告'),
        subtitle: Text((data['content'] as String? ?? '').substring(
          0,
          ((data['content'] as String? ?? '').length < 60
              ? (data['content'] as String? ?? '').length
              : 60),
        )),
        onTap: () => setState(() => _content = data['content'] as String? ?? ''),
      ),
    );
  }
}
