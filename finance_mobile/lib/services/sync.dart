import 'dart:convert';

import '../db/database.dart';
import 'api.dart';

class SyncService {
  static Future<int> pushDirty(ApiClient api) async {
    final rows = await LocalDb.dirtyRows();
    final changes = rows.map((row) {
      return <String, dynamic>{
        'table': row['table_name'],
        'row_id': row['row_id'],
        'data': jsonDecode(row['data_json'] as String),
        'deleted': row['deleted'] == 1,
        'updated_at': (row['updated_at'] as num?)?.toDouble() ?? 0,
      };
    }).toList();
    if (changes.isEmpty) return 0;
    final result = await api.push(changes);
    await LocalDb.clearDirty();
    return result['accepted'] as int? ?? 0;
  }

  static Future<void> fullSync(ApiClient api) async {
    await pushDirty(api);
    final snapshot = await api.snapshot();
    await LocalDb.clearAllEntities();
    final tables = snapshot['tables'] as Map<String, dynamic>? ?? {};
    tables.forEach((table, items) {
      for (final item in items as List) {
        final map = item as Map<String, dynamic>;
        LocalDb.upsertEntity(
          table,
          map['row_id'] as int,
          (map['data'] as Map<String, dynamic>?) ?? {},
          deleted: map['deleted'] == true,
          updatedAt: (map['updated_at'] as num?)?.toDouble() ?? 0,
          dirty: false,
        );
      }
    });
    await LocalDb.setMeta(
      'last_sync',
      (snapshot['since'] as int? ?? 0).toString(),
    );
  }

  static Future<void> pullDelta(ApiClient api) async {
    final last = int.tryParse(await LocalDb.meta('last_sync') ?? '0') ?? 0;
    final result = await api.pull(last);
    final changes = result['changes'] as List? ?? [];
    for (final item in changes) {
      final map = item as Map<String, dynamic>;
      final table = map['table'] as String;
      final rowId = map['row_id'] as int;
      if (map['deleted'] == true) {
        await LocalDb.deleteEntity(table, rowId);
      } else {
        await LocalDb.upsertEntity(
          table,
          rowId,
          (map['data'] as Map<String, dynamic>?) ?? {},
          updatedAt: (map['updated_at'] as num?)?.toDouble() ?? 0,
          dirty: false,
        );
      }
    }
    await LocalDb.setMeta('last_sync', (result['since'] as int? ?? 0).toString());
  }
}
