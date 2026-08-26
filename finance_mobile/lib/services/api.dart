import 'dart:convert';

import 'package:http/http.dart' as http;

class ApiClient {
  final String baseUrl;
  final String token;

  ApiClient({required this.baseUrl, required this.token});

  static Future<String> login(String baseUrl, String password) async {
    final uri = Uri.parse('${baseUrl.trim().replaceAll(RegExp(r'/$'), '')}/api/v1/auth/token');
    final resp = await http
        .post(uri, headers: {'Content-Type': 'application/json'}, body: jsonEncode({'password': password}))
        .timeout(const Duration(seconds: 10));
    if (resp.statusCode != 200) {
      throw Exception('登录失败：${resp.statusCode}');
    }
    final data = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    return data['token'] as String;
  }

  Future<Map<String, dynamic>> _send(
    String method,
    String path, {
    Object? body,
  }) async {
    final uri = Uri.parse('$baseUrl$path');
    final headers = {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $token',
    };
    late http.Response resp;
    if (method == 'GET') {
      resp = await http.get(uri, headers: headers).timeout(const Duration(seconds: 15));
    } else {
      resp = await http
          .post(uri, headers: headers, body: jsonEncode(body))
          .timeout(const Duration(seconds: 20));
    }
    if (resp.statusCode >= 400) {
      throw Exception('请求失败：${resp.statusCode} ${utf8.decode(resp.bodyBytes)}');
    }
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> snapshot() => _send('GET', '/api/v1/sync/snapshot');

  Future<Map<String, dynamic>> push(List<Map<String, dynamic>> changes) =>
      _send('POST', '/api/v1/sync/push', body: {'changes': changes});

  Future<Map<String, dynamic>> pull(int since) =>
      _send('GET', '/api/v1/sync/pull?since=$since');

  Future<Map<String, dynamic>> quote(String symbol, String assetType) => _send(
        'GET',
        '/api/v1/market/quote?symbol=${Uri.encodeComponent(symbol)}&asset_type=${Uri.encodeComponent(assetType)}',
      );

  Future<Map<String, dynamic>> gold() => _send('GET', '/api/v1/market/gold');

  Future<Map<String, dynamic>> checkUpdate() => _send('GET', '/api/v1/update');

  Future<Map<String, dynamic>> generateReport(
    String reportType,
    String periodLabel,
  ) =>
      _send(
        'POST',
        '/api/v1/report/generate',
        body: {
          'report_type': reportType,
          'period_label': periodLabel,
        },
      );
}
