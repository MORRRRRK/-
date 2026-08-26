import 'package:flutter/material.dart';

import 'expense_page.dart';
import 'functions_page.dart';
import 'holdings_page.dart';
import 'overview_page.dart';
import 'planning_page.dart';
import 'reports_page.dart';
import 'salary_page.dart';
import 'settings_page.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  int _tab = 0;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _tab,
        children: [
          FunctionsPage(onOpen: _openModule),
          const SettingsPage(),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (value) => setState(() => _tab = value),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.apps), label: '功能'),
          NavigationDestination(icon: Icon(Icons.settings_outlined), label: '设置'),
        ],
      ),
    );
  }

  void _openModule(int index) {
    if (index == 4) {
      setState(() => _tab = 1);
      return;
    }
    if (index == 3) return;
    final Widget page = switch (index) {
      0 => const OverviewPage(),
      1 => const ExpensePage(),
      2 => const HoldingsPage(),
      5 => const SalaryPage(),
      6 => const PlanningPage(),
      7 => const ReportsPage(),
      _ => const OverviewPage(),
    };
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => page),
    );
  }
}
