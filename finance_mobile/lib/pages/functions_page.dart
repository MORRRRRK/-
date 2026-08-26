import 'package:flutter/material.dart';

class FunctionsPage extends StatelessWidget {
  const FunctionsPage({super.key, required this.onOpen});

  final ValueChanged<int> onOpen;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('功能')),
      body: GridView.count(
        padding: const EdgeInsets.all(16),
        crossAxisCount: 2,
        mainAxisSpacing: 12,
        crossAxisSpacing: 12,
        children: [
          _item(context, Icons.dashboard_outlined, '资产总览', 0, const Color(0xFF2563EB)),
          _item(context, Icons.account_balance_wallet_outlined, '开支管理', 1, const Color(0xFF059669)),
          _item(context, Icons.trending_up, '持仓管理', 2, const Color(0xFFD97706)),
          _item(context, Icons.payments_outlined, '工资管理', 5, const Color(0xFF7C3AED)),
          _item(context, Icons.flag_outlined, '资产规划', 6, const Color(0xFF0D9488)),
          _item(context, Icons.article_outlined, '智能报告', 7, const Color(0xFFDC2626)),
          _item(context, Icons.settings_outlined, '设置', 4, const Color(0xFF475569)),
        ],
      ),
    );
  }

  Widget _item(
    BuildContext context,
    IconData icon,
    String title,
    int index,
    Color color,
  ) {
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: () => onOpen(index),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 36, color: color),
            const SizedBox(height: 8),
            Text(title, style: const TextStyle(fontSize: 15)),
          ],
        ),
      ),
    );
  }
}
