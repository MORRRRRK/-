import 'dart:convert';

import 'package:flutter/material.dart';

import '../db/database.dart';

class ExpensePage extends StatefulWidget {
  const ExpensePage({super.key});

  @override
  State<ExpensePage> createState() => _ExpensePageState();
}

class _ExpensePageState extends State<ExpensePage> {
  int _year = DateTime.now().year;
  List<Map<String, Object?>> _items = [];
  final Map<int, Map<String, TextEditingController>> _controllers = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final items = await LocalDb.entities('large_items');
    if (!mounted) return;
    setState(() {
      _items = items;
      _controllers.clear();
    });
  }

  Future<Map<String, dynamic>?> _monthData(int month) async {
    final rowId = _year * 100 + month;
    final data = await LocalDb.entityData('monthly_records', rowId);
    if (data.isEmpty) {
      return {'year': _year, 'month': month};
    }
    return data;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('开支管理'), actions: [
        IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
      ]),
      body: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          DropdownButtonFormField<int>(
            initialValue: _year,
            decoration: const InputDecoration(labelText: '年份'),
            items: [for (var y = _year - 3; y <= _year; y++) DropdownMenuItem(value: y, child: Text('$y'))],
            onChanged: (v) {
              if (v != null) setState(() => _year = v);
            },
          ),
          const SizedBox(height: 8),
          for (var month = 1; month <= 12; month++)
            _MonthCard(
              key: ValueKey('$_year-$month'),
              year: _year,
              month: month,
              onLoad: () => _monthData(month),
              onReload: _load,
            ),
          const SizedBox(height: 12),
          Row(
            children: [
              const Text('大笔收支', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
              const Spacer(),
              IconButton(onPressed: _addItem, icon: const Icon(Icons.add)),
            ],
          ),
          for (final item in _items) _itemCard(item),
        ],
      ),
    );
  }

  Widget _itemCard(Map<String, Object?> row) {
    final data = jsonDecode(row['data_json'] as String) as Map<String, dynamic>;
    final name = data['name'] as String? ?? '';
    final amount = (data['amount'] as num?)?.toDouble() ?? 0;
    final type = data['item_type'] == 'income' ? '收入' : '支出';
    return Card(
      child: ListTile(
        title: Text(name),
        subtitle: Text('${data['item_date'] ?? ''} · $type'),
        trailing: Text(
          amount.toStringAsFixed(2),
          style: TextStyle(
            color: data['item_type'] == 'income' ? Colors.green : Colors.red,
            fontWeight: FontWeight.bold,
          ),
        ),
        onLongPress: () => _deleteItem(row['row_id'] as int),
      ),
    );
  }

  Future<void> _addItem() async {
    final nameController = TextEditingController();
    final amountController = TextEditingController();
    final type = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('新增收支'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(controller: nameController, decoration: const InputDecoration(labelText: '名称')),
            TextField(
              controller: amountController,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: '金额'),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, 'expense'), child: const Text('支出')),
          TextButton(onPressed: () => Navigator.pop(context, 'income'), child: const Text('收入')),
        ],
      ),
    );
    if (type == null) return;
    final amount = double.tryParse(amountController.text) ?? 0;
    final now = DateTime.now().millisecondsSinceEpoch.toDouble();
    await LocalDb.upsertEntity(
      'large_items',
      now.toInt(),
      {
        'item_date': DateTime.now().toIso8601String().substring(0, 10),
        'name': nameController.text.trim(),
        'amount': amount,
        'item_type': type,
        'note': '',
      },
      updatedAt: now,
    );
    await _load();
  }

  Future<void> _deleteItem(int rowId) async {
    await LocalDb.upsertEntity(
      'large_items',
      rowId,
      {},
      deleted: true,
      updatedAt: DateTime.now().millisecondsSinceEpoch.toDouble(),
    );
    await _load();
  }
}

class _MonthCard extends StatefulWidget {
  const _MonthCard({
    super.key,
    required this.year,
    required this.month,
    required this.onLoad,
    required this.onReload,
  });

  final int year;
  final int month;
  final Future<Map<String, dynamic>?> Function() onLoad;
  final VoidCallback onReload;

  @override
  State<_MonthCard> createState() => _MonthCardState();
}

class _MonthCardState extends State<_MonthCard> {
  final Map<String, TextEditingController> _controllers = {};

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    final data = await widget.onLoad() ?? {};
    for (final key in ['salary', 'rent', 'monthly_expense', 'forced_deposit']) {
      _controllers[key] = TextEditingController(
        text: (data[key] as num?)?.toStringAsFixed(2) ?? '',
      );
    }
    if (mounted) setState(() {});
  }

  Future<void> _save(String key, String value) async {
    final parsed = double.tryParse(value.trim()) ?? 0;
    final now = DateTime.now().millisecondsSinceEpoch.toDouble();
    final base = await widget.onLoad() ?? {};
    base[key] = parsed;
    LocalDb.upsertEntity(
      'monthly_records',
      widget.year * 100 + widget.month,
      base,
      updatedAt: now,
    );
    widget.onReload();
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${widget.month} 月', style: const TextStyle(fontWeight: FontWeight.bold)),
            Wrap(
              spacing: 8,
              children: [
                for (final entry in [
                  ('salary', '月工资'),
                  ('rent', '房租'),
                  ('monthly_expense', '每月支出'),
                  ('forced_deposit', '存款'),
                ])
                  SizedBox(
                    width: 140,
                    child: TextField(
                      controller: _controllers[entry.$1],
                      keyboardType: TextInputType.number,
                      decoration: InputDecoration(labelText: entry.$2, isDense: true),
                      onChanged: (v) => _save(entry.$1, v),
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
