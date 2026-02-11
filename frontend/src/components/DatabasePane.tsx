import "@xyflow/react/dist/style.css";

import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Connection,
  type Edge,
  type EdgeMouseHandler,
  type Node,
  type NodeMouseHandler,
} from "@xyflow/react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { dbSchemaApply, dbSchemaGet, dbSchemaReview } from "@/services/dbSchema";
import type { DbSchema, DbTable } from "@/types/dbSchema";

const TYPE_OPTIONS = [
  { label: "Text", value: "text" },
  { label: "Number", value: "integer" },
  { label: "Boolean", value: "boolean" },
  { label: "Date", value: "date" },
  { label: "JSON", value: "jsonb" },
  { label: "UUID", value: "uuid" },
  { label: "Timestamp", value: "timestamp with time zone" },
] as const;

const FK_RULES = ["NO ACTION", "RESTRICT", "CASCADE", "SET NULL", "SET DEFAULT"] as const;

type TableNodeData = {
  table: DbTable;
  selectedTable: string | null;
  selectedColumn: string | null;
  onSelect: (tableName: string, columnName?: string) => void;
};

type DefaultMode = "none" | "value" | "now";

const asRecord = (v: unknown): Record<string, unknown> | null =>
  v && typeof v === "object" && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : null;

const cloneSchema = (schema: DbSchema): DbSchema =>
  JSON.parse(JSON.stringify(schema)) as DbSchema;

const titleCase = (value: string): string =>
  value
    .replace(/[_-]+/g, " ")
    .trim()
    .replace(/\s+/g, " ")
    .replace(/\b\w/g, (m) => m.toUpperCase());

const toSnakeCase = (value: string, fallback = "item"): string => {
  const raw = (value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  const base = raw || fallback;
  const prefixed = /^[a-z]/.test(base) ? base : `${fallback}_${base}`;
  return prefixed.slice(0, 63);
};

const dedupeName = (base: string, used: Set<string>): string => {
  if (!used.has(base)) {
    used.add(base);
    return base;
  }
  let idx = 2;
  while (idx < 10_000) {
    const suffix = `_${idx}`;
    const candidate = `${base.slice(0, 63 - suffix.length)}${suffix}`;
    if (!used.has(candidate)) {
      used.add(candidate);
      return candidate;
    }
    idx += 1;
  }
  return `${base.slice(0, 58)}_${Date.now().toString(36).slice(-4)}`;
};

const columnKey = (table: string, column: string): string => `${table}.${column}`;

const inferDefaultMode = (value: unknown): DefaultMode => {
  if (value == null || value === "") return "none";
  const obj = asRecord(value);
  if (obj && String(obj.raw || "").trim().toLowerCase() === "now()") return "now";
  return "value";
};

const formatDefaultInput = (value: unknown): string => {
  if (value == null) return "";
  const obj = asRecord(value);
  if (obj && typeof obj.raw === "string") return String(obj.raw);
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
};

const parseTypedDefault = (
  columnType: string,
  raw: string
): { ok: true; value: unknown } | { ok: false; error: string } => {
  const t = (columnType || "").toLowerCase();
  const text = raw.trim();
  if (!text) return { ok: true, value: null };

  if (t === "boolean") {
    if (text.toLowerCase() === "true") return { ok: true, value: true };
    if (text.toLowerCase() === "false") return { ok: true, value: false };
    return { ok: false, error: "Use true or false." };
  }
  if (["integer", "bigint", "serial", "bigserial"].includes(t)) {
    const n = Number(text);
    if (!Number.isInteger(n)) return { ok: false, error: "Use a whole number." };
    return { ok: true, value: n };
  }
  if (["numeric", "real", "double precision"].includes(t)) {
    const n = Number(text);
    if (Number.isNaN(n)) return { ok: false, error: "Use a valid number." };
    return { ok: true, value: n };
  }
  if (t === "jsonb") {
    try {
      return { ok: true, value: JSON.parse(text) };
    } catch {
      return { ok: false, error: "Use valid JSON." };
    }
  }
  return { ok: true, value: text };
};

const canUseNowDefault = (columnType: string): boolean => {
  const t = (columnType || "").toLowerCase();
  return (
    t.includes("timestamp") ||
    t === "date" ||
    t === "time" ||
    t === "time with time zone" ||
    t === "time without time zone"
  );
};

const defaultInputPlaceholder = (columnType: string): string => {
  const t = (columnType || "").toLowerCase();
  if (t === "boolean") return "true or false";
  if (["integer", "bigint", "serial", "bigserial"].includes(t)) return "e.g. 10";
  if (["numeric", "real", "double precision"].includes(t)) return "e.g. 9.99";
  if (t === "jsonb") return '{"key":"value"}';
  if (t === "uuid") return "e.g. 550e8400-e29b-41d4-a716-446655440000";
  if (canUseNowDefault(t)) return "e.g. 2026-02-11T12:00:00Z";
  return "Type a default value";
};

const TableNodeCard = ({ data }: { data: TableNodeData }) => {
  const table = data.table;
  return (
    <div
      className="rounded-md border bg-white shadow-md min-w-[220px]"
      style={{ borderColor: data.selectedTable === table.name ? "#2563eb" : "#d1d5db" }}
    >
      <div
        className="px-3 py-2 border-b bg-gray-100 text-sm font-semibold cursor-pointer"
        onClick={() => data.onSelect(table.name)}
      >
        {table.label}
      </div>
      <div className="px-2 py-1">
        {table.columns.map((col) => {
          const selected =
            data.selectedTable === table.name && data.selectedColumn === col.name;
          return (
            <div
              key={`${table.name}:${col.name}`}
              className="relative flex items-center justify-between text-xs rounded px-1.5 py-1 cursor-pointer"
              style={{
                background: selected ? "#eff6ff" : "transparent",
              }}
              onClick={() => data.onSelect(table.name, col.name)}
            >
              <Handle
                type="target"
                position={Position.Left}
                id={`in:${col.name}`}
                style={{ width: 8, height: 8, left: -5, background: "#64748b" }}
              />
              <span className="truncate">
                {col.label}
                {col.is_primary ? " (PK)" : ""}
              </span>
              <span className="text-[10px] text-gray-500 ml-2">{col.type}</span>
              <Handle
                type="source"
                position={Position.Right}
                id={`out:${col.name}`}
                style={{ width: 8, height: 8, right: -5, background: "#64748b" }}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
};

export const DatabasePane = ({ projectId }: { projectId: string }) => {
  const [loading, setLoading] = useState(true);
  const [reviewing, setReviewing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("");
  const [schemaVersion, setSchemaVersion] = useState<string>("");
  const [draft, setDraft] = useState<DbSchema | null>(null);
  const [search, setSearch] = useState("");
  const [selectedTable, setSelectedTable] = useState<string | null>(null);
  const [selectedColumn, setSelectedColumn] = useState<string | null>(null);
  const [selectedRelationship, setSelectedRelationship] = useState<string | null>(null);
  const [newTableLabel, setNewTableLabel] = useState("");
  const [newColumnLabel, setNewColumnLabel] = useState("");
  const [newColumnType, setNewColumnType] = useState<string>("text");
  const [relationshipTargetTable, setRelationshipTargetTable] = useState<string>("");
  const [relationshipFromColumn, setRelationshipFromColumn] = useState<string>("");
  const [relationshipToColumn, setRelationshipToColumn] = useState<string>("");
  const [relationshipOnDelete, setRelationshipOnDelete] = useState<string>("NO ACTION");
  const [relationshipOnUpdate, setRelationshipOnUpdate] = useState<string>("NO ACTION");
  const [defaultModeByColumn, setDefaultModeByColumn] = useState<Record<string, DefaultMode>>(
    {}
  );
  const [defaultInputByColumn, setDefaultInputByColumn] = useState<Record<string, string>>(
    {}
  );
  const [defaultErrorByColumn, setDefaultErrorByColumn] = useState<Record<string, string>>(
    {}
  );
  const [reviewText, setReviewText] = useState<string>("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [sqlPreview, setSqlPreview] = useState<string[]>([]);
  const [lastApplied, setLastApplied] = useState<string>("");

  const loadSchema = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await dbSchemaGet(projectId);
      setDraft(cloneSchema(res.schema));
      setSchemaVersion(res.version);
      setStatus("Schema loaded");
      setWarnings([]);
      setSqlPreview([]);
      setReviewText("");
      setNewTableLabel("");
      setDefaultModeByColumn({});
      setDefaultInputByColumn({});
      setDefaultErrorByColumn({});
      setRelationshipOnDelete("NO ACTION");
      setRelationshipOnUpdate("NO ACTION");
      setSelectedRelationship(null);
      setSelectedColumn(null);
      setSelectedTable(res.schema.tables[0]?.name || null);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "failed_to_load_schema";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void loadSchema();
  }, [loadSchema]);

  const tableMap = useMemo(() => {
    const map = new Map<string, DbTable>();
    for (const t of draft?.tables || []) map.set(t.name, t);
    return map;
  }, [draft]);

  const selectedTableObj = selectedTable ? tableMap.get(selectedTable) || null : null;
  const selectedRelObj = useMemo(() => {
    if (!selectedRelationship || !draft) return null;
    return draft.relationships.find((r) => r.name === selectedRelationship) || null;
  }, [draft, selectedRelationship]);

  useEffect(() => {
    if (!selectedTableObj) {
      setRelationshipFromColumn("");
      return;
    }
    if (
      !relationshipFromColumn ||
      !selectedTableObj.columns.some((c) => c.name === relationshipFromColumn)
    ) {
      setRelationshipFromColumn(selectedTableObj.columns[0]?.name || "");
    }
  }, [selectedTableObj, relationshipFromColumn]);

  useEffect(() => {
    if (!relationshipTargetTable || !draft) {
      setRelationshipToColumn("");
      return;
    }
    const t = draft.tables.find((x) => x.name === relationshipTargetTable);
    if (!t) {
      setRelationshipToColumn("");
      return;
    }
    if (!relationshipToColumn || !t.columns.some((c) => c.name === relationshipToColumn)) {
      const preferred = t.columns.find((c) => c.name === "id")?.name || t.columns[0]?.name || "";
      setRelationshipToColumn(preferred);
    }
  }, [draft, relationshipTargetTable, relationshipToColumn]);

  const filteredTables = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q || !draft) return draft?.tables || [];
    return draft.tables.filter(
      (t) =>
        t.name.toLowerCase().includes(q) ||
        t.label.toLowerCase().includes(q) ||
        t.columns.some(
          (c) => c.name.toLowerCase().includes(q) || c.label.toLowerCase().includes(q)
        )
    );
  }, [draft, search]);

  const nodeTypes = useMemo(() => ({ tableNode: TableNodeCard }), []);
  const hasValidationErrors = useMemo(
    () => Object.values(defaultErrorByColumn).some((v) => !!v),
    [defaultErrorByColumn]
  );

  const nodes: Node<TableNodeData>[] = useMemo(() => {
    return (draft?.tables || []).map((t) => ({
      id: t.name,
      type: "tableNode",
      position: {
        x: Number(t.position?.x ?? 0),
        y: Number(t.position?.y ?? 0),
      },
      data: {
        table: t,
        selectedTable,
        selectedColumn,
        onSelect: (tableName: string, columnName?: string) => {
          setSelectedRelationship(null);
          setSelectedTable(tableName);
          setSelectedColumn(columnName || null);
        },
      },
    }));
  }, [draft?.tables, selectedTable, selectedColumn]);

  const edges: Edge[] = useMemo(() => {
    return (draft?.relationships || []).map((r) => ({
      id: r.name,
      source: r.from_table,
      sourceHandle: `out:${r.from_column}`,
      target: r.to_table,
      targetHandle: `in:${r.to_column}`,
      animated: false,
      markerEnd: {
        type: MarkerType.ArrowClosed,
      },
      style:
        selectedRelationship === r.name
          ? { stroke: "#2563eb", strokeWidth: 2 }
          : { stroke: "#64748b", strokeWidth: 1.5 },
      label: r.name,
      labelStyle: { fontSize: 10 },
    }));
  }, [draft?.relationships, selectedRelationship]);

  const updateDraft = useCallback((fn: (prev: DbSchema) => DbSchema) => {
    setDraft((prev) => {
      if (!prev) return prev;
      return fn(cloneSchema(prev));
    });
  }, []);

  const addTable = useCallback((label: string) => {
    if (!draft) return;
    const trimmed = label.trim();
    if (!trimmed) return;
    const used = new Set(draft.tables.map((t) => t.name));
    const name = dedupeName(toSnakeCase(trimmed, "table"), used);

    updateDraft((prev) => {
      prev.tables.push({
        name,
        label: titleCase(trimmed),
        position: { x: 96 + prev.tables.length * 42, y: 96 + prev.tables.length * 24 },
        columns: [
          {
            name: "id",
            label: "Id",
            type: "bigserial",
            nullable: false,
            is_primary: true,
          },
        ],
      });
      return prev;
    });
    setSelectedRelationship(null);
    setSelectedTable(name);
    setSelectedColumn("id");
    setNewTableLabel("");
  }, [draft, updateDraft]);

  const deleteTable = useCallback(
    (tableName: string) => {
      if (!draft) return;
      if (!window.confirm(`Delete table "${tableName}"?`)) return;
      updateDraft((prev) => {
        prev.tables = prev.tables.filter((t) => t.name !== tableName);
        prev.relationships = prev.relationships.filter(
          (r) => r.from_table !== tableName && r.to_table !== tableName
        );
        return prev;
      });
      if (selectedTable === tableName) {
        setSelectedTable(null);
        setSelectedColumn(null);
      }
      setDefaultModeByColumn((prev) =>
        Object.fromEntries(Object.entries(prev).filter(([k]) => !k.startsWith(`${tableName}.`)))
      );
      setDefaultInputByColumn((prev) =>
        Object.fromEntries(Object.entries(prev).filter(([k]) => !k.startsWith(`${tableName}.`)))
      );
      setDefaultErrorByColumn((prev) =>
        Object.fromEntries(Object.entries(prev).filter(([k]) => !k.startsWith(`${tableName}.`)))
      );
      setSelectedRelationship(null);
    },
    [draft, selectedTable, updateDraft]
  );

  const addColumn = useCallback(() => {
    if (!selectedTableObj || !newColumnLabel.trim()) return;
    const used = new Set(selectedTableObj.columns.map((c) => c.name));
    const colName = dedupeName(toSnakeCase(newColumnLabel, "col"), used);

    updateDraft((prev) => {
      const t = prev.tables.find((x) => x.name === selectedTableObj.name);
      if (!t) return prev;
      t.columns.push({
        name: colName,
        label: titleCase(newColumnLabel),
        type: newColumnType,
        nullable: true,
      });
      return prev;
    });

    setSelectedColumn(colName);
    setNewColumnLabel("");
  }, [newColumnLabel, newColumnType, selectedTableObj, updateDraft]);

  const deleteColumn = useCallback(
    (columnName: string) => {
      if (!selectedTableObj) return;
      if (!window.confirm(`Delete column "${selectedTableObj.name}.${columnName}"?`)) return;
      updateDraft((prev) => {
        const t = prev.tables.find((x) => x.name === selectedTableObj.name);
        if (!t) return prev;
        t.columns = t.columns.filter((c) => c.name !== columnName);
        prev.relationships = prev.relationships.filter(
          (r) =>
            !(
              (r.from_table === selectedTableObj.name && r.from_column === columnName) ||
              (r.to_table === selectedTableObj.name && r.to_column === columnName)
            )
        );
        return prev;
      });
      const key = columnKey(selectedTableObj.name, columnName);
      setDefaultModeByColumn((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
      setDefaultInputByColumn((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
      setDefaultErrorByColumn((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
      if (selectedColumn === columnName) setSelectedColumn(null);
    },
    [selectedTableObj, selectedColumn, updateDraft]
  );

  const setColumnDefaultMode = useCallback(
    (tableName: string, colName: string, mode: DefaultMode) => {
      const k = columnKey(tableName, colName);
      setDefaultModeByColumn((prev) => ({ ...prev, [k]: mode }));
      setDefaultErrorByColumn((prev) => ({ ...prev, [k]: "" }));

      updateDraft((prev) => {
        const t = prev.tables.find((x) => x.name === tableName);
        const col = t?.columns.find((x) => x.name === colName);
        if (!col) return prev;
        if (mode === "none") {
          col.default = null;
          return prev;
        }
        if (mode === "now") {
          col.default = { raw: "now()" };
          return prev;
        }
        // "value": leave current value unless we have explicit input.
        const raw = defaultInputByColumn[k] ?? formatDefaultInput(col.default);
        const parsed = parseTypedDefault(col.type, raw);
        if (parsed.ok) {
          col.default = parsed.value;
        }
        return prev;
      });
    },
    [defaultInputByColumn, updateDraft]
  );

  const setColumnDefaultInput = useCallback(
    (tableName: string, colName: string, columnType: string, raw: string) => {
      const k = columnKey(tableName, colName);
      setDefaultInputByColumn((prev) => ({ ...prev, [k]: raw }));
      const parsed = parseTypedDefault(columnType, raw);
      if (!parsed.ok) {
        setDefaultErrorByColumn((prev) => ({ ...prev, [k]: parsed.error }));
        return;
      }
      setDefaultErrorByColumn((prev) => ({ ...prev, [k]: "" }));
      updateDraft((prev) => {
        const t = prev.tables.find((x) => x.name === tableName);
        const col = t?.columns.find((x) => x.name === colName);
        if (col) col.default = parsed.value;
        return prev;
      });
    },
    [updateDraft]
  );

  const addRelationship = useCallback(
    (
      fromTable: string,
      fromColumn: string,
      toTable: string,
      toColumn: string,
      onDelete = "NO ACTION",
      onUpdate = "NO ACTION"
    ) => {
      if (!draft) return;
      if (!fromTable || !fromColumn || !toTable || !toColumn) return;
      const exists = draft.relationships.some(
        (r) =>
          r.from_table === fromTable &&
          r.from_column === fromColumn &&
          r.to_table === toTable &&
          r.to_column === toColumn
      );
      if (exists) return;

      const used = new Set(draft.relationships.map((r) => r.name));
      const relName = dedupeName(
        toSnakeCase(`${fromTable}_${fromColumn}_to_${toTable}`, "fk"),
        used
      );

      updateDraft((prev) => {
        prev.relationships.push({
          name: relName,
          from_table: fromTable,
          from_column: fromColumn,
          to_table: toTable,
          to_column: toColumn,
          on_delete: onDelete,
          on_update: onUpdate,
        });
        return prev;
      });

      setSelectedRelationship(relName);
      setSelectedTable(null);
      setSelectedColumn(null);
      setRelationshipOnDelete("NO ACTION");
      setRelationshipOnUpdate("NO ACTION");
    },
    [draft, updateDraft]
  );

  const onConnect = useCallback(
    (conn: Connection) => {
      if (!conn.source || !conn.target || !conn.sourceHandle || !conn.targetHandle) {
        return;
      }
      const fromCol = conn.sourceHandle.replace(/^out:/, "");
      const toCol = conn.targetHandle.replace(/^in:/, "");
      addRelationship(conn.source, fromCol, conn.target, toCol);
    },
    [addRelationship]
  );

  const onNodeClick: NodeMouseHandler = useCallback((_evt, node) => {
    setSelectedRelationship(null);
    setSelectedTable(node.id);
    setSelectedColumn(null);
  }, []);

  const onEdgeClick: EdgeMouseHandler = useCallback((_evt, edge) => {
    setSelectedRelationship(edge.id);
    setSelectedTable(null);
    setSelectedColumn(null);
  }, []);

  const onNodeDragStop: NodeMouseHandler = useCallback((_evt, node) => {
    updateDraft((prev) => {
      const t = prev.tables.find((x) => x.name === node.id);
      if (t) {
        t.position = {
          x: Number(node.position.x || 0),
          y: Number(node.position.y || 0),
        };
      }
      return prev;
    });
  }, [updateDraft]);

  const runReview = useCallback(async () => {
    if (!draft) return;
    setReviewing(true);
    setError(null);
    try {
      const res = await dbSchemaReview(projectId, {
        base_version: schemaVersion,
        draft,
      });
      setReviewText(res.review?.summary || "");
      setWarnings(res.warnings || []);
      setSqlPreview(res.sql_preview || []);
      setStatus("Review updated");
    } catch (e: unknown) {
      const err = e as { status?: number; data?: unknown };
      if (err?.status === 409) {
        setStatus("Schema changed remotely; reloading.");
        await loadSchema();
        return;
      }
      setError(e instanceof Error ? e.message : "review_failed");
    } finally {
      setReviewing(false);
    }
  }, [draft, loadSchema, projectId, schemaVersion]);

  const runApply = useCallback(async () => {
    if (!draft) return;
    setApplying(true);
    setError(null);
    try {
      let res;
      try {
        res = await dbSchemaApply(projectId, {
          base_version: schemaVersion,
          draft,
          confirm_destructive: false,
        });
      } catch (e: unknown) {
        const err = e as { status?: number; data?: unknown };
        const data = asRecord(err?.data);
        if (
          err?.status === 409 &&
          data &&
          data.error === "destructive_confirmation_required"
        ) {
          const details = Array.isArray(data.destructive_details)
            ? data.destructive_details.map((x) => String(x)).join("\n")
            : "Potential destructive changes.";
          const ok = window.confirm(
            `This apply includes destructive changes:\n\n${details}\n\nProceed?`
          );
          if (!ok) {
            setApplying(false);
            return;
          }
          res = await dbSchemaApply(projectId, {
            base_version: schemaVersion,
            draft,
            confirm_destructive: true,
          });
        } else {
          throw e;
        }
      }

      setDraft(cloneSchema(res.schema));
      setSchemaVersion(res.version || res.new_version);
      setDefaultModeByColumn({});
      setDefaultInputByColumn({});
      setDefaultErrorByColumn({});
      setWarnings(res.warnings || []);
      setSqlPreview(res.sql_preview || []);
      setLastApplied(new Date().toLocaleString());
      const sha = res.git_sync?.commit_sha;
      setStatus(sha ? `Applied and synced (${String(sha).slice(0, 8)})` : "Applied");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "apply_failed");
    } finally {
      setApplying(false);
    }
  }, [draft, projectId, schemaVersion]);

  if (loading || !draft) {
    return <div style={{ padding: 16 }}>Loading database schema...</div>;
  }

  const otherTables = draft.tables.filter((t) => t.name !== selectedTableObj?.name);

  return (
    <div className="flex flex-col h-full min-h-0 bg-card">
      <div className="border-b px-3 py-2 flex items-center gap-3">
        <div className="text-sm font-semibold">Database</div>
        <div className="text-xs text-muted-foreground">Schema status: {status || "Idle"}</div>
        <div className="text-xs text-muted-foreground">Version: {schemaVersion || "-"}</div>
        <div className="text-xs text-muted-foreground">
          Last applied: {lastApplied || "Not yet"}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => void loadSchema()}>
            Reload
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => void runReview()}
            disabled={reviewing || hasValidationErrors}
          >
            {reviewing ? "Reviewing..." : "Review with AI"}
          </Button>
          <Button size="sm" onClick={() => void runApply()} disabled={applying || hasValidationErrors}>
            {applying ? "Applying..." : "Apply changes"}
          </Button>
        </div>
      </div>

      {error ? (
        <div className="border-b px-3 py-2 text-sm text-red-700 bg-red-50">Error: {error}</div>
      ) : null}
      {!error && hasValidationErrors ? (
        <div className="border-b px-3 py-2 text-sm text-amber-800 bg-amber-50">
          Fix invalid default values before review/apply.
        </div>
      ) : null}

      <div className="flex-1 min-h-0 grid [grid-template-columns:260px_1fr_360px]">
        <div className="border-r p-3 min-h-0 overflow-auto">
          <div className="flex gap-2 mb-2">
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search tables"
            />
          </div>

          <div className="border rounded p-2 mb-3 bg-blue-50">
            <div className="text-xs font-semibold mb-1">
              {draft.tables.length ? "Create another table" : "Create your first table"}
            </div>
            <div className="text-[11px] text-muted-foreground mb-2">
              Use a friendly name. We create a safe technical name automatically.
            </div>
            <div className="flex gap-2">
              <Input
                value={newTableLabel}
                onChange={(e) => setNewTableLabel(e.target.value)}
                placeholder="e.g. Customers"
              />
              <Button
                size="sm"
                onClick={() => addTable(newTableLabel)}
                disabled={!newTableLabel.trim()}
              >
                Create
              </Button>
            </div>
          </div>

          {!draft.tables.length ? (
            <div className="border rounded p-2 mb-3 bg-emerald-50">
              <div className="text-xs font-semibold mb-1">Quick walkthrough</div>
              <ol className="text-[11px] list-decimal pl-4 space-y-1">
                <li>Create a table in the box above.</li>
                <li>Add columns in the right panel.</li>
                <li>Connect tables by dragging column dots in the diagram.</li>
                <li>Click "Review with AI", then "Apply changes".</li>
              </ol>
            </div>
          ) : null}

          <div className="space-y-2">
            {filteredTables.map((t) => (
              <div
                key={t.name}
                className="border rounded p-2 cursor-pointer"
                style={{
                  borderColor: selectedTable === t.name ? "#2563eb" : "#d1d5db",
                  background: selectedTable === t.name ? "#eff6ff" : "transparent",
                }}
                onClick={() => {
                  setSelectedRelationship(null);
                  setSelectedTable(t.name);
                  setSelectedColumn(null);
                }}
              >
                <div className="text-sm font-medium">{t.label}</div>
                <div className="text-xs text-muted-foreground">{t.name}</div>
                <div className="text-xs text-muted-foreground">{t.columns.length} columns</div>
                <Button
                  size="sm"
                  variant="destructive"
                  className="mt-2"
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteTable(t.name);
                  }}
                >
                  Delete
                </Button>
              </div>
            ))}
          </div>

          <div className="mt-4">
            {warnings.length ? (
              <div className="border rounded p-2 text-xs bg-amber-50">
                <div className="font-semibold mb-1">Warnings</div>
                <ul className="list-disc pl-4">
                  {warnings.map((w, idx) => (
                    <li key={`w-${idx}`}>{w}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </div>

        <div className="min-h-0">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView
            onConnect={onConnect}
            onPaneClick={() => {
              setSelectedRelationship(null);
            }}
            onNodeClick={onNodeClick}
            onEdgeClick={onEdgeClick}
            onNodeDragStop={onNodeDragStop}
          >
            <Background gap={20} size={1} />
            <Controls />
          </ReactFlow>
        </div>

        <div className="border-l p-3 min-h-0 overflow-auto">
          {selectedRelObj ? (
            <div className="space-y-3">
              <div className="text-sm font-semibold">Relationship</div>
              <div className="text-xs text-muted-foreground">{selectedRelObj.name}</div>
              <div className="text-xs">
                {selectedRelObj.from_table}.{selectedRelObj.from_column} -&gt; {selectedRelObj.to_table}.
                {selectedRelObj.to_column}
              </div>
              <label className="text-xs block">
                On delete
                <select
                  className="mt-1 w-full border rounded px-2 py-1 text-sm"
                  value={selectedRelObj.on_delete || "NO ACTION"}
                  onChange={(e) => {
                    const next = e.target.value;
                    updateDraft((prev) => {
                      const rel = prev.relationships.find((r) => r.name === selectedRelObj.name);
                      if (rel) rel.on_delete = next;
                      return prev;
                    });
                  }}
                >
                  {FK_RULES.map((r) => (
                    <option key={`od-${r}`} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-xs block">
                On update
                <select
                  className="mt-1 w-full border rounded px-2 py-1 text-sm"
                  value={selectedRelObj.on_update || "NO ACTION"}
                  onChange={(e) => {
                    const next = e.target.value;
                    updateDraft((prev) => {
                      const rel = prev.relationships.find((r) => r.name === selectedRelObj.name);
                      if (rel) rel.on_update = next;
                      return prev;
                    });
                  }}
                >
                  {FK_RULES.map((r) => (
                    <option key={`ou-${r}`} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </label>
              <Button
                variant="destructive"
                onClick={() => {
                  if (!window.confirm(`Delete relationship "${selectedRelObj.name}"?`)) return;
                  updateDraft((prev) => {
                    prev.relationships = prev.relationships.filter(
                      (r) => r.name !== selectedRelObj.name
                    );
                    return prev;
                  });
                  setSelectedRelationship(null);
                }}
              >
                Delete relationship
              </Button>
            </div>
          ) : selectedTableObj ? (
            <div className="space-y-3">
              <div className="text-sm font-semibold">Table</div>

              <label className="text-xs block">
                Friendly label
                <Input
                  value={selectedTableObj.label}
                  onChange={(e) => {
                    const next = e.target.value;
                    updateDraft((prev) => {
                      const t = prev.tables.find((x) => x.name === selectedTableObj.name);
                      if (t) t.label = next;
                      return prev;
                    });
                  }}
                />
              </label>

              <div className="text-xs text-muted-foreground">
                Technical name: <span className="font-mono">{selectedTableObj.name}</span>
              </div>

              <div className="border rounded p-2 space-y-2">
                <div className="text-xs font-semibold">Columns</div>
                {selectedTableObj.columns.map((c) => {
                  const key = columnKey(selectedTableObj.name, c.name);
                  const defaultMode = defaultModeByColumn[key] ?? inferDefaultMode(c.default);
                  const defaultInput = defaultInputByColumn[key] ?? formatDefaultInput(c.default);
                  const defaultError = defaultErrorByColumn[key] || "";
                  return (
                    <div
                      key={`${selectedTableObj.name}:${c.name}`}
                      className="border rounded p-2 bg-gray-50"
                      style={{ borderColor: selectedColumn === c.name ? "#2563eb" : "#e5e7eb" }}
                      onClick={() => setSelectedColumn(c.name)}
                    >
                      <div className="grid grid-cols-2 gap-2">
                        <label className="text-xs block">
                          Label
                          <Input
                            value={c.label}
                            onChange={(e) => {
                              const next = e.target.value;
                              updateDraft((prev) => {
                                const t = prev.tables.find((x) => x.name === selectedTableObj.name);
                                const col = t?.columns.find((x) => x.name === c.name);
                                if (col) col.label = next;
                                return prev;
                              });
                            }}
                          />
                        </label>
                        <label className="text-xs block">
                          Type
                          <select
                            className="mt-1 w-full border rounded px-2 py-1 text-sm"
                            value={c.type}
                            onChange={(e) => {
                              const next = e.target.value;
                              updateDraft((prev) => {
                                const t = prev.tables.find((x) => x.name === selectedTableObj.name);
                                const col = t?.columns.find((x) => x.name === c.name);
                                if (col) col.type = next;
                                return prev;
                              });
                              const raw = defaultInputByColumn[key] ?? formatDefaultInput(c.default);
                              const mode = defaultModeByColumn[key] ?? inferDefaultMode(c.default);
                              if (mode === "value") {
                                const parsed = parseTypedDefault(next, raw);
                                setDefaultErrorByColumn((prev) => ({
                                  ...prev,
                                  [key]: parsed.ok ? "" : parsed.error,
                                }));
                                if (parsed.ok) {
                                  updateDraft((prev) => {
                                    const t = prev.tables.find(
                                      (x) => x.name === selectedTableObj.name
                                    );
                                    const col = t?.columns.find((x) => x.name === c.name);
                                    if (col) col.default = parsed.value;
                                    return prev;
                                  });
                                }
                              } else if (mode === "now" && !canUseNowDefault(next)) {
                                setColumnDefaultMode(selectedTableObj.name, c.name, "none");
                              }
                            }}
                          >
                            {TYPE_OPTIONS.map((opt) => (
                              <option key={`type-${opt.value}`} value={opt.value}>
                                {opt.label}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="text-xs block">
                          Nullable
                          <input
                            className="ml-2"
                            type="checkbox"
                            checked={!!c.nullable}
                            onChange={(e) => {
                              const next = e.target.checked;
                              updateDraft((prev) => {
                                const t = prev.tables.find((x) => x.name === selectedTableObj.name);
                                const col = t?.columns.find((x) => x.name === c.name);
                                if (col) col.nullable = next;
                                return prev;
                              });
                            }}
                            disabled={!!c.is_primary}
                          />
                        </label>
                        <label className="text-xs block">
                          Default behavior
                          <select
                            className="mt-1 w-full border rounded px-2 py-1 text-sm"
                            value={defaultMode}
                            onChange={(e) =>
                              setColumnDefaultMode(
                                selectedTableObj.name,
                                c.name,
                                e.target.value as DefaultMode
                              )
                            }
                          >
                            <option value="none">No default</option>
                            <option value="value">Set a value</option>
                            {canUseNowDefault(c.type) ? (
                              <option value="now">Use current time when created</option>
                            ) : null}
                          </select>
                        </label>
                        {defaultMode === "value" ? (
                          <label className="text-xs block col-span-2">
                            Default value
                            <Input
                              className={
                                defaultError ? "border-red-500 focus-visible:ring-red-300" : ""
                              }
                              value={defaultInput}
                              placeholder={defaultInputPlaceholder(c.type)}
                              onChange={(e) =>
                                setColumnDefaultInput(
                                  selectedTableObj.name,
                                  c.name,
                                  c.type,
                                  e.target.value
                                )
                              }
                            />
                            {defaultError ? (
                              <div className="mt-1 text-[11px] text-red-600">{defaultError}</div>
                            ) : (
                              <div className="mt-1 text-[11px] text-muted-foreground">
                                We validate this value based on column type.
                              </div>
                            )}
                          </label>
                        ) : null}
                        {defaultMode === "now" ? (
                          <div className="text-[11px] text-muted-foreground col-span-2">
                            This column will auto-fill with the current date/time.
                          </div>
                        ) : null}
                      </div>
                      <div className="mt-2 flex items-center justify-between">
                        <div className="text-[11px] text-muted-foreground font-mono">{c.name}</div>
                        <Button
                          size="sm"
                          variant="destructive"
                          disabled={!!c.is_primary}
                          onClick={(e) => {
                            e.stopPropagation();
                            deleteColumn(c.name);
                          }}
                        >
                          Delete column
                        </Button>
                      </div>
                    </div>
                  );
                })}

                <div className="border rounded p-2">
                  <div className="text-xs font-semibold mb-2">Add column</div>
                  <div className="grid grid-cols-2 gap-2">
                    <Input
                      placeholder="Column label"
                      value={newColumnLabel}
                      onChange={(e) => setNewColumnLabel(e.target.value)}
                    />
                    <select
                      className="border rounded px-2 py-1 text-sm"
                      value={newColumnType}
                      onChange={(e) => setNewColumnType(e.target.value)}
                    >
                      {TYPE_OPTIONS.map((opt) => (
                        <option key={`new-type-${opt.value}`} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <Button className="mt-2" size="sm" onClick={addColumn}>
                    Add column
                  </Button>
                </div>
              </div>

              <div className="border rounded p-2 space-y-2">
                <div className="text-xs font-semibold">Add relationship</div>
                <div className="text-[11px] text-muted-foreground">
                  Connect records between tables, like Orders belonging to Customers.
                </div>
                <label className="text-xs block">
                  From column
                  <select
                    className="mt-1 w-full border rounded px-2 py-1 text-sm"
                    value={relationshipFromColumn}
                    onChange={(e) => setRelationshipFromColumn(e.target.value)}
                  >
                    {selectedTableObj.columns.map((c) => (
                      <option key={`from-${c.name}`} value={c.name}>
                        {c.label} ({c.name})
                      </option>
                    ))}
                  </select>
                </label>
                <label className="text-xs block">
                  Target table
                  <select
                    className="mt-1 w-full border rounded px-2 py-1 text-sm"
                    value={relationshipTargetTable}
                    onChange={(e) => setRelationshipTargetTable(e.target.value)}
                  >
                    <option value="">Select table</option>
                    {otherTables.map((t) => (
                      <option key={`to-table-${t.name}`} value={t.name}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="text-xs block">
                  Target column
                  <select
                    className="mt-1 w-full border rounded px-2 py-1 text-sm"
                    value={relationshipToColumn}
                    onChange={(e) => setRelationshipToColumn(e.target.value)}
                    disabled={!relationshipTargetTable}
                  >
                    <option value="">Select column</option>
                    {(draft.tables.find((t) => t.name === relationshipTargetTable)?.columns || []).map(
                      (c) => (
                        <option key={`to-col-${c.name}`} value={c.name}>
                          {c.label} ({c.name})
                        </option>
                      )
                    )}
                  </select>
                </label>
                <label className="text-xs block">
                  When parent is deleted
                  <select
                    className="mt-1 w-full border rounded px-2 py-1 text-sm"
                    value={relationshipOnDelete}
                    onChange={(e) => setRelationshipOnDelete(e.target.value)}
                  >
                    {FK_RULES.map((r) => (
                      <option key={`new-od-${r}`} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="text-xs block">
                  When parent key changes
                  <select
                    className="mt-1 w-full border rounded px-2 py-1 text-sm"
                    value={relationshipOnUpdate}
                    onChange={(e) => setRelationshipOnUpdate(e.target.value)}
                  >
                    {FK_RULES.map((r) => (
                      <option key={`new-ou-${r}`} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </label>
                <Button
                  size="sm"
                  onClick={() =>
                    addRelationship(
                      selectedTableObj.name,
                      relationshipFromColumn,
                      relationshipTargetTable,
                      relationshipToColumn,
                      relationshipOnDelete,
                      relationshipOnUpdate
                    )
                  }
                  disabled={
                    !relationshipFromColumn ||
                    !relationshipTargetTable ||
                    !relationshipToColumn
                  }
                >
                  Add relationship
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              <div className="text-sm text-muted-foreground">
                Select a table or relationship from the diagram.
              </div>
              <div className="text-xs text-muted-foreground">
                Tip: Start by creating a table on the left, then click it here to add columns.
              </div>
            </div>
          )}

          <div className="mt-4 border-t pt-3">
            <div className="text-xs font-semibold mb-1">AI review</div>
            <div className="text-xs whitespace-pre-wrap">{reviewText || "No review yet."}</div>
          </div>

          <details className="mt-3 border rounded p-2">
            <summary className="text-xs font-semibold cursor-pointer">
              Advanced: Show SQL preview
            </summary>
            <pre className="mt-2 text-[11px] whitespace-pre-wrap max-h-[220px] overflow-auto">
              {(sqlPreview || []).join("\n") || "No SQL preview available."}
            </pre>
          </details>
        </div>
      </div>
    </div>
  );
};
