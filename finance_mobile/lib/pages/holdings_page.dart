import 'dart:convert';

import 'package:flutter/material.dart';

import '../db/database.dart';
import '../services/api.dart';

class HoldingsPage extends StatefulWidget {
  const HoldingsPage({super.key});

  @override
  State<HoldingsPage> createState() => _HoldingsPageState();
}

class _HoldingsPageState extends State<HoldingsPage> {
  List<Map<String, Object?>> _holdings = [];
  List<Map<String, Object?>> _gold = [];
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final holdings = await LocalDb.entities('holdings');
    final gold = await LocalDb.entities('gold_accounts');
    if (!mounted) return;
    setState(() {
      _holdings = holdings;
      _gold = gold;
    });
  }

  Future<ApiClient?> _client() async {
    final baseUrl = await LocalDb.meta('server_url') ?? '';
    final token = await LocalDb.meta('token') ?? '';
    if (baseUrl.isEmpty || token.isEmpty) return null;
    return ApiClient(baseUrl: baseUrl, token: token);
  }

  Future<void> _refreshQuotes() async {
    final api = await _client();
    if (api == null) {
      _toast('请先在设置中登录同步服务');
      return;
    }
    setState(() => _busy = true);
    try {
      for (final row in _holdings) {
        final data = jsonDecode(row['data_json'] as String) as Map<String, dynamic>;
        final symbol = (data['symbol'] as String? ?? '').trim();
        final assetType = (data['asset_type'] as String? ?? '').trim();
        if (symbol.isEmpty || assetType.isEmpty) continue;
        final result = await api.quote(symbol, assetType);
        final price = (result['price'] as num?)?.toDouble();
        if (price != null) {
          final shares = (data['shares'] as num?)?.toDouble() ?? 0;
          data['last_price'] = price;
          if (shares > 0) {
            data['holding_value'] = double.parse((shares * price).toStringAsFixed(2));
          }
          await LocalDb.upsertEntity(
            'holdings',
            row['row_id'] as int,
            data,
            updatedAt: DateTime.now().millisecondsSinceEpoch.toDouble(),
          );
        }
      }
      final goldResult = await api.gold();
      final goldPrice = (goldResult['price'] as num?)?.toDouble();
      if (goldPrice != null) {
        for (final row in _gold) {
          final data = jsonDecode(row['data_json'] as String) as Map<String, dynamic>;
          data['last_price'] = goldPrice;
          await LocalDb.upsertEntity(
            'gold_accounts',
            row['row_id'] as int,
            data,
            updatedAt: DateTime.now().millisecondsSinceEpoch.toDouble(),
          );
        }
      }
      await _load();
      _toast('行情刷新完成');
    } catch (e) {
      _toast('刷新失败：$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _addHolding() async {
    final name = TextEditingController();
    final symbol = TextEditingController();
    final shares = TextEditingController();
    String assetType = 'stock';
    await showDialog<void>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('新增持仓'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(controller: name, decoration: const InputDecoration(labelText: '名称')),
              TextField(controller: symbol, decoration: const InputDecoration(labelText: '代码')),
              TextField(
                controller: shares,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: '份额'),
              ),
              DropdownButtonFormField<String>(
                initialValue: assetType,
                items: const [
                  DropdownMenuItem(value: 'stock', child: Text('股票')),
                  DropdownMenuItem(value: 'fund_exchange', child: Text('场内基金')),
                  DropdownMenuItem(value: 'fund_otc', child: Text('场外基金')),
                  DropdownMenuItem(value: 'gold_etf', child: Text('黄金 ETF')),
                ],
                onChanged: (v) => setDialogState(() => assetType = v ?? 'stock'),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context), child: const Text('取消')),
            TextButton(
              onPressed: () async {
                final now = DateTime.now().millisecondsSinceEpoch.toDouble();
                await LocalDb.upsertEntity(
                  'holdings',
                  now.toInt(),
                  {
                    'name': name.text.trim(),
                    'symbol': symbol.text.trim(),
                    'asset_type': assetType,
                    'shares': double.tryParse(shares.text) ?? 0,
                    'holding_value': 0,
                    'holding_profit': 0,
                    'cumulative_profit': 0,
                    'cost_basis': null,
                    'last_price': null,
                    'invest_plan': 0,
                    'invest_time': '',
                  },
                  updatedAt: now,
                );
                if (context.mounted) Navigator.pop(context);
                await _load();
              },
              child: const Text('保存'),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _deleteHolding(int rowId) async {
    await LocalDb.upsertEntity(
      'holdings',
      rowId,
      {},
      deleted: true,
      updatedAt: DateTime.now().millisecondsSinceEpoch.toDouble(),
    );
    await _load();
  }

  void _toast(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('持仓管理'),
        actions: [
          IconButton(onPressed: _busy ? null : _refreshQuotes, icon: const Icon(Icons.refresh)),
          IconButton(onPressed: _addHolding, icon: const Icon(Icons.add)),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          for (final row in _holdings) _holdingCard(row),
          const SizedBox(height: 12),
          const Text('黄金账户', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          for (final row in _gold) _goldCard(row),
        ],
      ),
    );
  }

  Widget _holdingCard(Map<String, Object?> row) {
    final data = jsonDecode(row['data_json'] as String) as Map<String, dynamic>;
    final name = data['name'] as String? ?? '';
    final symbol = data['symbol'] as String? ?? '';
    final shares = (data['shares'] as num?)?.toDouble() ?? 0;
    final value = (data['holding_value'] as num?)?.toDouble() ?? 0;
    final cum = (data['cumulative_profit'] as num?)?.toDouble() ?? 0;
    var net = (data['last_price'] as num?)?.toDouble();
    if (net == null && shares > 0) net = value / shares;
    return Card(
      child: ListTile(
        title: Text(name),
        subtitle: Text('$symbol · ${shares.toStringAsFixed(2)} 份'),
        trailing: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text('净值 ${net?.toStringAsFixed(4) ?? '-'}'),
            Text(
              '市值 ${value.toStringAsFixed(2)}',
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),
            Text('收益 ${cum.toStringAsFixed(2)}'),
          ],
        ),
        onLongPress: () => _deleteHolding(row['row_id'] as int),
      ),
    );
  }

  Widget _goldCard(Map<String, Object?> row) {
    final data = jsonDecode(row['data_json'] as String) as Map<String, dynamic>;
    final grams = (data['grams'] as num?)?.toDouble() ?? 0;
    final price = (data['last_price'] as num?)?.toDouble() ?? 0;
    final value = grams * price;
    return Card(
      child: ListTile(
        title: Text(data['name'] as String? ?? '黄金账户'),
        subtitle: Text('${grams.toStringAsFixed(3)} 克 · 参考金价 ${price.toStringAsFixed(2)}'),
        trailing: Text(
          '市值 ${value.toStringAsFixed(2)}',
          style: const TextStyle(fontWeight: FontWeight.bold),
        ),
        onLongPress: () async {
          await LocalDb.upsertEntity(
            'gold_accounts',
            row['row_id'] as int,
            {},
            deleted: true,
            updatedAt: DateTime.now().millisecondsSinceEpoch.toDouble(),
          );
          await _load();
        },
      ),
    );
  }
}
