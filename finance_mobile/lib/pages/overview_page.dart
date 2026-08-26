import 'dart:convert';

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../db/database.dart';

class OverviewPage extends StatefulWidget {
  const OverviewPage({super.key});

  @override
  State<OverviewPage> createState() => _OverviewPageState();
}

class _OverviewPageState extends State<OverviewPage> {
  List<Map<String, Object?>> _monthly = [];
  List<Map<String, Object?>> _holdings = [];
  List<Map<String, Object?>> _gold = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final monthly = await LocalDb.entities('monthly_records');
    final holdings = await LocalDb.entities('holdings');
    final gold = await LocalDb.entities('gold_accounts');
    if (!mounted) return;
    setState(() {
      _monthly = monthly;
      _holdings = holdings;
      _gold = gold;
    });
  }

  Map<String, double> _monthTotals() {
    final totals = <String, double>{};
    for (final row in _monthly) {
      final data = jsonDecode(row['data_json'] as String) as Map<String, dynamic>;
      final month = (row['row_id'] as num).toInt() % 100;
      final salary = _num(data['salary']);
      final income = salary +
          _num(data['year_end_bonus']) +
          _num(data['subsidies']) +
          _num(data['reimbursements']);
      totals['income_$month'] = income;
      totals['expense_$month'] = _num(data['monthly_expense']);
      totals['deposit_$month'] = _num(data['forced_deposit']);
      totals['salary'] = _num(totals['salary']) + salary;
      totals['income'] = _num(totals['income']) + income;
      totals['deposits'] = _num(totals['deposits']) + _num(data['forced_deposit']);
    }
    return totals;
  }

  Map<String, double> _investSummary() {
    var holding = 0.0;
    var profit = 0.0;
    final categories = <String, double>{};
    for (final row in _holdings) {
      final data = jsonDecode(row['data_json'] as String) as Map<String, dynamic>;
      final value = _num(data['holding_value']);
      final cum = _num(data['cumulative_profit']);
      holding += value;
      profit += cum;
      categories[data['category'] as String? ?? '基金'] =
          _num(categories[data['category'] as String? ?? '基金']) + value;
    }
    var goldValue = 0.0;
    var goldProfit = 0.0;
    for (final row in _gold) {
      final data = jsonDecode(row['data_json'] as String) as Map<String, dynamic>;
      final grams = _num(data['grams']);
      final price = _num(data['last_price']);
      final cost = _num(data['cost_basis']);
      final value = grams * price;
      goldValue += value;
      goldProfit += value - cost;
    }
    categories['黄金账户'] = goldValue;
    return {
      'holding': holding + goldValue,
      'profit': profit + goldProfit,
      'categories': categories.values.fold(0.0, (a, b) => a + b),
    };
  }

  @override
  Widget build(BuildContext context) {
    final monthly = _monthTotals();
    final invest = _investSummary();
    final netWorth = monthly['deposits']! + invest['holding']!;
    return Scaffold(
      appBar: AppBar(title: const Text('资产总览'), actions: [
        IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
      ]),
      body: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          _cards(monthly, invest, netWorth),
          const SizedBox(height: 12),
          _barChart(monthly),
          const SizedBox(height: 12),
          _pieChart(monthly, invest),
        ],
      ),
    );
  }

  Widget _cards(Map<String, double> m, Map<String, double> i, double net) {
    return Row(
      children: [
        _card('净资产', net, Colors.blue),
        _card('累计存款', m['deposits']!, Colors.green),
        _card('投资持仓', i['holding']!, Colors.orange),
        _card('累计收益', i['profit']!, Colors.red),
      ],
    );
  }

  Widget _card(String title, double value, Color color) {
    return Expanded(
      child: Card(
        color: color.withValues(alpha: 0.12),
        child: Padding(
          padding: const EdgeInsets.all(8),
          child: Column(
            children: [
              Text(title, style: const TextStyle(fontSize: 12)),
              const SizedBox(height: 4),
              Text(
                value.toStringAsFixed(0),
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: color),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _barChart(Map<String, double> m) {
    final groups = List.generate(12, (index) {
      final month = index + 1;
      return BarChartGroupData(
        x: month,
        barRods: [
          BarChartRodData(
            toY: m['income_$month']!,
            color: Colors.blue,
            width: 6,
          ),
          BarChartRodData(
            toY: m['expense_$month']!,
            color: Colors.red,
            width: 6,
          ),
        ],
      );
    });
    return SizedBox(
      height: 220,
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(8),
          child: BarChart(
            BarChartData(
              maxY: _maxY(m),
              barGroups: groups,
              titlesData: const FlTitlesData(
                leftTitles: AxisTitles(),
                rightTitles: AxisTitles(),
                topTitles: AxisTitles(),
                bottomTitles: AxisTitles(
                  sideTitles: SideTitles(showTitles: false),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  double _maxY(Map<String, double> m) {
    var max = 1.0;
    for (var month = 1; month <= 12; month++) {
      max = _max(max, m['income_$month']!);
      max = _max(max, m['expense_$month']!);
    }
    return max * 1.1;
  }

  Widget _pieChart(Map<String, double> m, Map<String, double> i) {
    final values = <String, double>{
      '存款': m['deposits']!,
      '持仓': i['holding']!,
    };
    final sections = values.entries.map((e) {
      return PieChartSectionData(
        value: e.value,
        title: '${e.key}\n${e.value.toStringAsFixed(0)}',
        color: e.key == '存款' ? Colors.green : Colors.blue,
        radius: 40,
      );
    }).toList();
    return SizedBox(
      height: 220,
      child: Card(
        child: PieChart(
          PieChartData(
            sections: sections,
            sectionsSpace: 2,
            centerSpaceRadius: 36,
          ),
        ),
      ),
    );
  }

  double _num(Object? value) => (value as num?)?.toDouble() ?? 0;
  double _max(double a, double b) => a > b ? a : b;
}
