import 'dart:convert';

import 'package:path/path.dart';
import 'package:sqflite/sqflite.dart';

class LocalDb {
  static Database? _db;

  static Future<Database> get instance async {
    if (_db != null) return _db!;
    _db = await _open();
    return _db!;
  }

  static Future<void> init() async {
    await instance;
  }

  static Future<Database> _open() async {
    final path = join(await getDatabasesPath(), 'finance_mobile.db');
    return openDatabase(
      path,
      version: 1,
      onCreate: (db, version) async {
        await db.execute('''
          CREATE TABLE entities (
            table_name TEXT NOT NULL,
            row_id INTEGER NOT NULL,
            data_json TEXT NOT NULL DEFAULT '{}',
            deleted INTEGER NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL DEFAULT 0,
            dirty INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (table_name, row_id)
          )
        ''');
        await db.execute('''
          CREATE TABLE meta (
            key TEXT PRIMARY KEY,
            value TEXT
          )
        ''');
      },
    );
  }

  static Future<List<Map<String, Object?>>> entities(String table) async {
    final db = await instance;
    return db.query(
      'entities',
      where: 'table_name = ? AND deleted = 0',
      whereArgs: [table],
      orderBy: 'row_id',
    );
  }

  static Future<Map<String, dynamic>> entityData(
    String table,
    int rowId,
  ) async {
    final db = await instance;
    final rows = await db.query(
      'entities',
      where: 'table_name = ? AND row_id = ?',
      whereArgs: [table, rowId],
      limit: 1,
    );
    if (rows.isEmpty) return {};
    return jsonDecode(rows.first['data_json'] as String) as Map<String, dynamic>;
  }

  static Future<void> upsertEntity(
    String table,
    int rowId,
    Map<String, dynamic> data, {
    bool deleted = false,
    double updatedAt = 0,
    bool dirty = true,
  }) async {
    final db = await instance;
    await db.insert(
      'entities',
      {
        'table_name': table,
        'row_id': rowId,
        'data_json': jsonEncode(data),
        'deleted': deleted ? 1 : 0,
        'updated_at': updatedAt,
        'dirty': dirty ? 1 : 0,
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  static Future<void> deleteEntity(String table, int rowId) async {
    final db = await instance;
    await db.delete(
      'entities',
      where: 'table_name = ? AND row_id = ?',
      whereArgs: [table, rowId],
    );
  }

  static Future<void> clearAllEntities() async {
    final db = await instance;
    await db.delete('entities');
  }

  static Future<List<Map<String, Object?>>> dirtyRows() async {
    final db = await instance;
    return db.query('entities', where: 'dirty = 1');
  }

  static Future<void> markSynced(String table, int rowId) async {
    final db = await instance;
    await db.rawUpdate(
      'UPDATE entities SET dirty = 0 WHERE table_name = ? AND row_id = ?',
      [table, rowId],
    );
  }

  static Future<void> clearDirty() async {
    final db = await instance;
    await db.rawUpdate('UPDATE entities SET dirty = 0');
  }

  static Future<String?> meta(String key) async {
    final db = await instance;
    final rows = await db.query('meta', where: 'key = ?', whereArgs: [key]);
    return rows.isEmpty ? null : rows.first['value'] as String?;
  }

  static Future<void> setMeta(String key, String value) async {
    final db = await instance;
    await db.insert(
      'meta',
      {'key': key, 'value': value},
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }
}
