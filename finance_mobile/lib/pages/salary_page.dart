import 'dart:convert';

import 'package:flutter/material.dart';

import '../db/database.dart';

class SalaryPage extends StatefulWidget {
  const SalaryPage({super.key});

  @override
  State<SalaryPage> createState() => _SalaryPageState();
}

class _SalaryPageState extends State<SalaryPage> {
  int _year = DateTime.now().year;
  final _base = TextEditingController(text: '12266');
  final _thirteen = TextEditingController(text: '1');
  final _bonus = TextEditingController(text: '1');
  final _rentTier = TextEditingController(text: '1500');
  final _elderly = TextEditingController(text: '3000');
  final _children = TextEditingController(text: '0');
  final _infant = TextEditingController(text: '0');
  final _severe = TextEditingController(text: '0');
  final _custom = TextEditingController(text: '0');
  List<Map<String, Object?>> _insurance = [];
  String _result = '';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final insurance = await LocalDb.entities('insurance_items');
    if (!mounted) return;
    setState(() {
      _insurance = insurance.isEmpty
          ? [
              {'name': '公积金', 'base': '12266', 'personal_rate': '9', 'company_rate': '9', 'personal_fixed': ''},
              {'name': '养老', 'base': '12266', 'personal_rate': '8', 'company_rate': '16', 'personal_fixed': ''},
              {'name': '医保', 'base': '12266', 'personal_rate': '2', 'company_rate': '7', 'personal_fixed': ''},
              {'name': '大额医疗', 'base': '0', 'personal_rate': '0', 'company_rate': '0', 'personal_fixed': '5'},
              {'name': '生育', 'base': '12266', 'personal_rate': '0', 'company_rate': '0.8', 'personal_fixed': ''},
              {'name': '工伤', 'base': '12266', 'personal_rate': '0', 'company_rate': '1.35', 'personal_fixed': ''},
              {'name': '失业', 'base': '12266', 'personal_rate': '0.5', 'company_rate': '0.5', 'personal_fixed': ''},
            ]
          : insurance.map((r) => jsonDecode(r['data_json'] as String) as Map<String, dynamic>).toList();
    });
    _calc();
  }

  void _calc() {
    final base = double.tryParse(_base.text) ?? 0;
    final thirteen = double.tryParse(_thirteen.text) ?? 0;
    final bonus = double.tryParse(_bonus.text) ?? 0;
    final rent = double.tryParse(_rentTier.text) ?? 0;
    final elderly = double.tryParse(_elderly.text) ?? 0;
    final children = (double.tryParse(_children.text) ?? 0) * 2000;
    final infant = (double.tryParse(_infant.text) ?? 0) * 2000;
    final severe = double.tryParse(_severe.text) ?? 0;
    final custom = double.tryParse(_custom.text) ?? 0;
    var personalTotal = 0.0;
    var companyTotal = 0.0;
    for (final item in _insurance) {
      final itemBase = double.tryParse(item['base'] as String? ?? '') ?? 0;
      final pRate = (double.tryParse(item['personal_rate'] as String? ?? '') ?? 0) / 100;
      final cRate = (double.tryParse(item['company_rate'] as String? ?? '') ?? 0) / 100;
      final fixed = double.tryParse(item['personal_fixed'] as String? ?? '');
      personalTotal += fixed ?? itemBase * pRate;
      companyTotal += itemBase * cRate;
    }
    final totalSalary = base * 12 + base * thirteen + base * bonus;
    final gross = totalSalary - personalTotal * 12;
    final package = gross + companyTotal * 12;
    final taxable = gross -
        60000 -
        (rent + elderly + children + infant + custom) * 12 -
        severe;
    final tax = _incomeTax(taxable < 0 ? 0 : taxable);
    final net = totalSalary - personalTotal * 12 - tax;
    setState(() {
      _result = '总工资 $totalSalary\n'
          '个人缴纳(月) $personalTotal\n'
          '公司缴纳(月) $companyTotal\n'
          '税前收入 $gross\n'
          '总包 $package\n'
          '全年个税 $tax\n'
          '税后收入 $net';
    });
  }

  double _incomeTax(double taxable) {
    const brackets = [
      [36000.0, 0.03, 0.0],
      [144000.0, 0.10, 2520.0],
      [300000.0, 0.20, 16920.0],
      [420000.0, 0.25, 31920.0],
      [660000.0, 0.30, 52920.0],
      [960000.0, 0.35, 85920.0],
      [double.infinity, 0.45, 181920.0],
    ];
    for (final b in brackets) {
      if (taxable <= b[0]) return taxable * b[1] - b[2];
    }
    return 0;
  }

  Future<void> _save() async {
    final now = DateTime.now().millisecondsSinceEpoch.toDouble();
    await LocalDb.upsertEntity(
      'social_insurance_params',
      _year,
      {
        'year': _year,
        'monthly_salary': double.tryParse(_base.text) ?? 0,
        'thirteenth_coefficient': double.tryParse(_thirteen.text) ?? 0,
        'year_end_bonus_coefficient': double.tryParse(_bonus.text) ?? 0,
      },
      updatedAt: now,
    );
    await LocalDb.upsertEntity(
      'tax_params',
      _year,
      {
        'year': _year,
        'rent_tier': double.tryParse(_rentTier.text) ?? 0,
        'elderly_monthly': double.tryParse(_elderly.text) ?? 0,
        'children_education_count': int.tryParse(_children.text) ?? 0,
        'infant_care_count': int.tryParse(_infant.text) ?? 0,
        'severe_illness_annual': double.tryParse(_severe.text) ?? 0,
        'custom_deduction': double.tryParse(_custom.text) ?? 0,
      },
      updatedAt: now,
    );
    for (var i = 0; i < _insurance.length; i++) {
      await LocalDb.upsertEntity(
        'insurance_items',
        _year * 1000 + i,
        {..._insurance[i], 'year': _year},
        updatedAt: now,
      );
    }
    _toast('工资参数已保存');
  }

  void _toast(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('工资管理'),
        actions: [
          IconButton(onPressed: _calc, icon: const Icon(Icons.calculate_outlined)),
          IconButton(onPressed: _save, icon: const Icon(Icons.save_outlined)),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          DropdownButtonFormField<int>(
            initialValue: _year,
            items: [for (var y = _year - 3; y <= _year; y++) DropdownMenuItem(value: y, child: Text('$y'))],
            onChanged: (v) => setState(() => _year = v ?? _year),
          ),
          _field('基本工资（月）', _base),
          _field('13薪 xN', _thirteen),
          _field('年终奖 xN', _bonus),
          const SizedBox(height: 8),
          const Text('N险N金', style: TextStyle(fontWeight: FontWeight.bold)),
          for (var i = 0; i < _insurance.length; i++) _insuranceRow(i),
          const SizedBox(height: 8),
          const Text('专项附加扣除', style: TextStyle(fontWeight: FontWeight.bold)),
          _field('租房扣除/月', _rentTier),
          _field('赡养老人/月', _elderly),
          _field('子女教育人数', _children),
          _field('婴幼儿人数', _infant),
          _field('大病医疗年额', _severe),
          _field('其他扣除/月', _custom),
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Text(_result.isEmpty ? '填写后点计算' : _result),
            ),
          ),
        ],
      ),
    );
  }

  Widget _field(String label, TextEditingController controller) {
    return TextField(
      controller: controller,
      keyboardType: TextInputType.number,
      decoration: InputDecoration(labelText: label, isDense: true),
      onChanged: (_) => _calc(),
    );
  }

  Widget _insuranceRow(int index) {
    final item = _insurance[index];
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Row(
          children: [
            Expanded(
              flex: 2,
              child: TextFormField(
                initialValue: item['name'] as String? ?? '',
                decoration: const InputDecoration(labelText: '名称', isDense: true),
                onChanged: (v) => item['name'] = v,
              ),
            ),
            Expanded(
              child: TextFormField(
                initialValue: item['base'] as String? ?? '',
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: '基数', isDense: true),
                onChanged: (v) {
                  item['base'] = v;
                  _calc();
                },
              ),
            ),
            Expanded(
              child: TextFormField(
                initialValue: item['personal_rate'] as String? ?? '',
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: '个人%', isDense: true),
                onChanged: (v) {
                  item['personal_rate'] = v;
                  _calc();
                },
              ),
            ),
            Expanded(
              child: TextFormField(
                initialValue: item['company_rate'] as String? ?? '',
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: '公司%', isDense: true),
                onChanged: (v) {
                  item['company_rate'] = v;
                  _calc();
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}
