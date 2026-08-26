import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../db/database.dart';

class PlanningPage extends StatefulWidget {
  const PlanningPage({super.key});

  @override
  State<PlanningPage> createState() => _PlanningPageState();
}

class _PlanningPageState extends State<PlanningPage> {
  List<Map<String, Object?>> _goals = [];
  final _current = TextEditingController(text: '100000');
  final _monthly = TextEditingController(text: '5000');
  final _rate = TextEditingController(text: '3');
  final _years = TextEditingController(text: '5');
  final _target = TextEditingController(text: '200000');
  final _months = TextEditingController(text: '36');
  final _targetRate = TextEditingController(text: '2');
  String _projection = '-';
  String _saving = '-';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final goals = await LocalDb.entities('goals');
    if (!mounted) return;
    setState(() => _goals = goals);
  }

  void _calcProjection() {
    final current = double.tryParse(_current.text) ?? 0;
    final monthly = double.tryParse(_monthly.text) ?? 0;
    final rate = (double.tryParse(_rate.text) ?? 0) / 100;
    final years = double.tryParse(_years.text) ?? 0;
    final months = years * 12;
    final rm = rate / 12;
    var future = current * math.pow(1 + rate, years);
    if (rm > 0) {
      future += monthly * ((math.pow(1 + rm, months) - 1) / rm);
    } else {
      future += monthly * months;
    }
    setState(() => _projection = future.toStringAsFixed(2));
  }

  void _calcSaving() {
    final target = double.tryParse(_target.text) ?? 0;
    final months = double.tryParse(_months.text) ?? 0;
    final rate = (double.tryParse(_targetRate.text) ?? 0) / 100;
    final rm = rate / 12;
    var required = 0.0;
    if (months > 0) {
      required = rm > 0
          ? target * rm / (math.pow(1 + rm, months) - 1)
          : target / months;
    }
    setState(() => _saving = required.toStringAsFixed(2));
  }

  Future<void> _addGoal() async {
    final name = TextEditingController();
    final target = TextEditingController();
    final current = TextEditingController();
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('新增储蓄目标'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(controller: name, decoration: const InputDecoration(labelText: '目标名称')),
            TextField(
              controller: target,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: '目标金额'),
            ),
            TextField(
              controller: current,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: '已存金额'),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('取消')),
          TextButton(
            onPressed: () async {
              final now = DateTime.now().millisecondsSinceEpoch.toDouble();
              await LocalDb.upsertEntity(
                'goals',
                now.toInt(),
                {
                  'name': name.text.trim(),
                  'target_amount': double.tryParse(target.text) ?? 0,
                  'current_amount': double.tryParse(current.text) ?? 0,
                  'monthly_saving': 0,
                  'note': '',
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
    );
  }

  Future<void> _deleteGoal(int rowId) async {
    await LocalDb.upsertEntity(
      'goals',
      rowId,
      {},
      deleted: true,
      updatedAt: DateTime.now().millisecondsSinceEpoch.toDouble(),
    );
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('资产规划'),
        actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
          IconButton(onPressed: _addGoal, icon: const Icon(Icons.add)),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                children: [
                  const Text('净资产增长模拟', style: TextStyle(fontWeight: FontWeight.bold)),
                  TextField(controller: _current, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: '当前资产')),
                  TextField(controller: _monthly, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: '每月投入')),
                  TextField(controller: _rate, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: '年化收益率 %')),
                  TextField(controller: _years, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: '年数')),
                  FilledButton(onPressed: _calcProjection, child: const Text('计算')),
                  Text('约 $_projection 元'),
                ],
              ),
            ),
          ),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                children: [
                  const Text('目标倒推每月存款', style: TextStyle(fontWeight: FontWeight.bold)),
                  TextField(controller: _target, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: '目标金额')),
                  TextField(controller: _months, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: '目标月数')),
                  TextField(controller: _targetRate, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: '年化收益率 %')),
                  FilledButton(onPressed: _calcSaving, child: const Text('计算')),
                  Text('每月需存约 $_saving 元'),
                ],
              ),
            ),
          ),
          const Text('储蓄目标', style: TextStyle(fontWeight: FontWeight.bold)),
          for (final row in _goals) _goalCard(row),
        ],
      ),
    );
  }

  Widget _goalCard(Map<String, Object?> row) {
    final data = jsonDecode(row['data_json'] as String) as Map<String, dynamic>;
    final name = data['name'] as String? ?? '';
    final target = (data['target_amount'] as num?)?.toDouble() ?? 0;
    final current = (data['current_amount'] as num?)?.toDouble() ?? 0;
    return Card(
      child: ListTile(
        title: Text(name),
        subtitle: Text('已存 ${current.toStringAsFixed(0)} / 目标 ${target.toStringAsFixed(0)}'),
        onLongPress: () => _deleteGoal(row['row_id'] as int),
      ),
    );
  }
}
