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
import { Textarea } from "@/components/ui/textarea";
import {
  dbSchemaApply,
  dbSchemaGet,
  dbSchemaIntent,
  dbSchemaReview,
} from "@/services/dbSchema";
import type {
  CitizenChangeCard,
  ClarificationOption,
  DbColumn,
  DbRelationship,
  DbSchema,
  DbTable,
} from "@/types/dbSchema";

const TYPE_OPTIONS = [
  { label: "Text", value: "text" },
  { label: "Number", value: "integer" },
  { label: "Boolean", value: "boolean" },
  { label: "Date", value: "date" },
  { label: "JSON", value: "jsonb" },
  { label: "UUID", value: "uuid" },
  { label: "Timestamp", value: "timestamp with time zone" },
  { label: "Decimal", value: "numeric" },
  { label: "Big Number", value: "bigint" },
] as const;

const FK_RULES = ["NO ACTION", "RESTRICT", "CASCADE", "SET NULL", "SET DEFAULT"] as const;

const SUGGESTED_INTENTS = [
  "Add customers and orders",
  "Track order status",
  "Link orders to customers",
] as const;

const FIELD_PRESETS = [
  { key: "name", label: "Name", type: "text", nullable: false as const },
  { key: "email", label: "Email", type: "text", nullable: false as const },
  { key: "phone", label: "Phone", type: "text", nullable: true as const },
  { key: "price", label: "Price", type: "numeric", nullable: false as const },
  { key: "date", label: "Date", type: "date", nullable: false as const },
  {
    key: "status",
    label: "Status",
    type: "text",
    nullable: false as const,
    default: "new",
  },
  {
    key: "active",
    label: "Active",
    type: "boolean",
    nullable: false as const,
    default: true,
  },
  { key: "notes", label: "Notes", type: "text", nullable: true as const },
  { key: "custom", label: "Custom", type: "text", nullable: true as const },
] as const;

type FieldPresetKey = (typeof FIELD_PRESETS)[number]["key"];

type RelationKind = "one_to_many" | "one_to_one";

const RELATION_OPTIONS = [
  {
    value: "one_to_many" as const,
    label: "One-to-many",
    helper: "Many records in this table can belong to one record in the target table.",
  },
  {
    value: "one_to_one" as const,
    label: "One-to-one",
    helper: "One record in this table links to one record in the target table.",
  },
];

type TableNodeData = {
  table: DbTable;
  selectedTable: string | null;
  onSelect: (tableName: string) => void;
};

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

const singularize = (value: string): string => {
  const v = (value || "").trim().toLowerCase();
  if (v.endsWith("ies") && v.length > 3) return `${v.slice(0, -3)}y`;
  if (v.endsWith("s") && v.length > 1) return v.slice(0, -1);
  return v;
};

const presetByKey = new Map(
  FIELD_PRESETS.map((preset) => [preset.key, preset] as const)
);

const inferPreset = (col: DbColumn): FieldPresetKey => {
  const t = String(col.type || "").toLowerCase();
  if (t === "numeric") return "price";
  if (t === "date") return "date";
  if (t === "boolean") return "active";
  if (t === "text") {
    const key = toSnakeCase(String(col.label || col.name || "")).toLowerCase();
    if (key.includes("email")) return "email";
    if (key.includes("name")) return "name";
    if (key.includes("phone")) return "phone";
    if (key.includes("status")) return "status";
    if (key.includes("note")) return "notes";
  }
  return "custom";
};

const tableLabel = (schema: DbSchema | null, tableName: string): string => {
  if (!schema) return tableName;
  const t = schema.tables.find((x) => x.name === tableName);
  return t?.label || tableName;
};

const relationSentence = (schema: DbSchema | null, rel: DbRelationship): string => {
  const from = tableLabel(schema, rel.from_table);
  const to = tableLabel(schema, rel.to_table);
  return `${from} belong to ${to}`;
};

const formatDefaultValue = (value: unknown): string => {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  const obj = asRecord(value);
  if (obj && typeof obj.raw === "string") return String(obj.raw);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
};

const parseDefaultValue = (columnType: string, raw: string): unknown => {
  const text = raw.trim();
  if (!text) return null;
  const t = String(columnType || "").toLowerCase();
  if (t === "boolean") {
    if (text.toLowerCase() === "true") return true;
    if (text.toLowerCase() === "false") return false;
    return text;
  }
  if (["integer", "bigint", "numeric", "real", "double precision"].includes(t)) {
    const n = Number(text);
    if (!Number.isNaN(n)) return n;
  }
  return text;
};

const TableNodeCard = ({ data }: { data: TableNodeData }) => {
  const table = data.table;
  const selected = data.selectedTable === table.name;
  return (
    <div
      className="rounded-md border bg-white shadow-md min-w-[220px]"
      style={{ borderColor: selected ? "#2563eb" : "#d1d5db" }}
    >
      <div
        className="px-3 py-2 border-b bg-gray-100 text-sm font-semibold cursor-pointer"
        onClick={() => data.onSelect(table.name)}
      >
        {table.label}
      </div>
      <div className="px-2 py-1">
        {table.columns.slice(0, 8).map((col) => (
          <div
            key={`${table.name}:${col.name}`}
            className="relative flex items-center justify-between text-xs rounded px-1.5 py-1"
          >
            <Handle
              type="target"
              position={Position.Left}
              id={`in:${col.name}`}
              style={{ width: 8, height: 8, left: -5, background: "#64748b" }}
            />
            <span className="truncate">
              {col.label}
              {col.is_primary ? " (ID)" : ""}
            </span>
            <Handle
              type="source"
              position={Position.Right}
              id={`out:${col.name}`}
              style={{ width: 8, height: 8, right: -5, background: "#64748b" }}
            />
          </div>
        ))}
        {table.columns.length > 8 ? (
          <div className="text-[10px] text-muted-foreground px-1.5 py-1">
            +{table.columns.length - 8} more fields
          </div>
        ) : null}
      </div>
    </div>
  );
};

export const DatabasePane = ({ projectId }: { projectId: string }) => {
  const [loading, setLoading] = useState(true);
  const [askingAi, setAskingAi] = useState(false);
  const [applying, setApplying] = useState(false);
  const [reviewingTech, setReviewingTech] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("");
  const [schemaVersion, setSchemaVersion] = useState<string>("");
  const [draft, setDraft] = useState<DbSchema | null>(null);
  const [search, setSearch] = useState("");
  const [selectedTable, setSelectedTable] = useState<string | null>(null);
  const [selectedRelationship, setSelectedRelationship] = useState<string | null>(null);

  const [intentText, setIntentText] = useState("");
  const [assistantMessage, setAssistantMessage] = useState("");
  const [changeCards, setChangeCards] = useState<CitizenChangeCard[]>([]);
  const [needsClarification, setNeedsClarification] = useState(false);
  const [clarificationQuestion, setClarificationQuestion] = useState("");
  const [clarificationOptions, setClarificationOptions] = useState<ClarificationOption[]>(
    []
  );

  const [warnings, setWarnings] = useState<string[]>([]);
  const [lastApplied, setLastApplied] = useState("");

  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [technicalReviewText, setTechnicalReviewText] = useState("");
  const [sqlPreview, setSqlPreview] = useState<string[]>([]);

  const [newTableLabel, setNewTableLabel] = useState("");
  const [newFieldLabel, setNewFieldLabel] = useState("");
  const [newFieldPreset, setNewFieldPreset] = useState<FieldPresetKey>("custom");
  const [relationTargetTable, setRelationTargetTable] = useState("");
  const [relationKind, setRelationKind] = useState<RelationKind>("one_to_many");

  const loadSchema = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await dbSchemaGet(projectId);
      setDraft(cloneSchema(res.schema));
      setSchemaVersion(res.version);
      setStatus("Schema loaded");
      setWarnings([]);
      setAssistantMessage("");
      setChangeCards([]);
      setNeedsClarification(false);
      setClarificationQuestion("");
      setClarificationOptions([]);
      setTechnicalReviewText("");
      setSqlPreview([]);
      setSelectedRelationship(null);
      setSelectedTable(res.schema.tables[0]?.name || null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "failed_to_load_schema");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void loadSchema();
  }, [loadSchema]);

  const updateDraft = useCallback((fn: (prev: DbSchema) => DbSchema) => {
    setDraft((prev) => {
      if (!prev) return prev;
      return fn(cloneSchema(prev));
    });
  }, []);

  const selectedTableObj = useMemo(
    () => draft?.tables.find((t) => t.name === selectedTable) || null,
    [draft, selectedTable]
  );

  const selectedRelationshipObj = useMemo(
    () => draft?.relationships.find((r) => r.name === selectedRelationship) || null,
    [draft, selectedRelationship]
  );

  const filteredTables = useMemo(() => {
    if (!draft) return [];
    const q = search.trim().toLowerCase();
    if (!q) return draft.tables;
    return draft.tables.filter((t) => {
      if (t.label.toLowerCase().includes(q)) return true;
      return t.columns.some((c) => c.label.toLowerCase().includes(q));
    });
  }, [draft, search]);

  const nodeTypes = useMemo(() => ({ tableNode: TableNodeCard }), []);

  const nodes: Node<TableNodeData>[] = useMemo(() => {
    return (draft?.tables || []).map((t) => ({
      id: t.name,
      type: "tableNode",
      position: { x: Number(t.position?.x || 0), y: Number(t.position?.y || 0) },
      data: {
        table: t,
        selectedTable,
        onSelect: (tableName: string) => {
          setSelectedRelationship(null);
          setSelectedTable(tableName);
        },
      },
    }));
  }, [draft?.tables, selectedTable]);

  const edges: Edge[] = useMemo(() => {
    return (draft?.relationships || []).map((rel) => ({
      id: rel.name,
      source: rel.from_table,
      sourceHandle: `out:${rel.from_column}`,
      target: rel.to_table,
      targetHandle: `in:${rel.to_column}`,
      markerEnd: { type: MarkerType.ArrowClosed },
      label: relationSentence(draft, rel),
      labelStyle: { fontSize: 10 },
      style:
        selectedRelationship === rel.name
          ? { stroke: "#2563eb", strokeWidth: 2 }
          : { stroke: "#64748b", strokeWidth: 1.5 },
    }));
  }, [draft, selectedRelationship]);

  const applyFieldPreset = useCallback(
    (presetKey: FieldPresetKey, label: string): Partial<DbColumn> => {
      const preset = presetByKey.get(presetKey) || presetByKey.get("custom");
      if (!preset) return { type: "text", nullable: true };
      const out: Partial<DbColumn> = {
        label: titleCase(label || preset.label),
        type: preset.type,
        nullable: preset.nullable,
      };
      if ("default" in preset) {
        out.default = preset.default;
      }
      return out;
    },
    []
  );

  const addTable = useCallback(
    (label: string) => {
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
      setNewTableLabel("");
      setStatus("Table added");
    },
    [draft, updateDraft]
  );

  const deleteTable = useCallback(
    (tableName: string) => {
      if (!draft) return;
      const tableFriendly = tableLabel(draft, tableName);
      const ok = window.confirm(
        `Delete ${tableFriendly}? This removes the table and its links when you apply.`
      );
      if (!ok) return;
      updateDraft((prev) => {
        prev.tables = prev.tables.filter((t) => t.name !== tableName);
        prev.relationships = prev.relationships.filter(
          (r) => r.from_table !== tableName && r.to_table !== tableName
        );
        return prev;
      });
      if (selectedTable === tableName) setSelectedTable(null);
      if (selectedRelationshipObj &&
        (selectedRelationshipObj.from_table === tableName ||
          selectedRelationshipObj.to_table === tableName)
      ) {
        setSelectedRelationship(null);
      }
      setStatus("Table removed from draft");
    },
    [draft, selectedRelationshipObj, selectedTable, updateDraft]
  );

  const addField = useCallback(() => {
    if (!selectedTableObj || !newFieldLabel.trim()) return;
    const label = newFieldLabel.trim();
    const presetData = applyFieldPreset(newFieldPreset, label);

    updateDraft((prev) => {
      const t = prev.tables.find((x) => x.name === selectedTableObj.name);
      if (!t) return prev;
      const used = new Set(t.columns.map((c) => c.name));
      const name = dedupeName(toSnakeCase(label, "field"), used);
      t.columns.push({
        name,
        label: titleCase(label),
        type: String(presetData.type || "text"),
        nullable: Boolean(presetData.nullable ?? true),
        default: presetData.default,
      });
      return prev;
    });

    setNewFieldLabel("");
    setStatus("Field added");
  }, [applyFieldPreset, newFieldLabel, newFieldPreset, selectedTableObj, updateDraft]);

  const deleteField = useCallback(
    (columnName: string) => {
      if (!selectedTableObj || !draft) return;
      const col = selectedTableObj.columns.find((c) => c.name === columnName);
      if (!col) return;
      const ok = window.confirm(
        `Delete field ${col.label}? This can remove data when applied.`
      );
      if (!ok) return;

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
      setStatus("Field removed from draft");
    },
    [draft, selectedTableObj, updateDraft]
  );

  const addBusinessRelationship = useCallback(
    (fromTableName: string, toTableName: string, kind: RelationKind) => {
      if (!draft || !fromTableName || !toTableName) return;
      let addedRelationship: string | null = null;
      let needsOneToOneNote = false;
      updateDraft((prev) => {
        const fromTable = prev.tables.find((t) => t.name === fromTableName);
        const toTable = prev.tables.find((t) => t.name === toTableName);
        if (!fromTable || !toTable) return prev;

        const parentSingular = singularize(toTable.name || toTable.label || "parent");
        const fkColName = toSnakeCase(`${parentSingular}_id`, "parent_id");
        if (!fromTable.columns.some((c) => c.name === fkColName)) {
          fromTable.columns.push({
            name: fkColName,
            label: `${titleCase(parentSingular)} Id`,
            type: "bigint",
            nullable: false,
          });
        }

        const exists = prev.relationships.some(
          (r) =>
            r.from_table === fromTable.name &&
            r.from_column === fkColName &&
            r.to_table === toTable.name &&
            r.to_column === "id"
        );
        if (exists) return prev;

        const used = new Set(prev.relationships.map((r) => r.name));
        const relName = dedupeName(
          toSnakeCase(`${fromTable.name}_${fkColName}_to_${toTable.name}`, "fk"),
          used
        );

        prev.relationships.push({
          name: relName,
          from_table: fromTable.name,
          from_column: fkColName,
          to_table: toTable.name,
          to_column: "id",
          on_delete: "NO ACTION",
          on_update: "NO ACTION",
        });
        addedRelationship = relName;
        if (kind === "one_to_one") {
          needsOneToOneNote = true;
        }
        return prev;
      });
      if (addedRelationship) {
        setSelectedRelationship(addedRelationship);
        setSelectedTable(null);
      }
      if (needsOneToOneNote) {
        setWarnings((w) => {
          if (w.some((x) => x.includes("One-to-one"))) {
            return w;
          }
          return [
            ...w,
            "One-to-one is represented as a single link. Unique constraints can be added in Advanced settings.",
          ];
        });
      }
      setStatus("Relationship added");
    },
    [draft, updateDraft]
  );

  const onConnect = useCallback(
    (conn: Connection) => {
      if (!conn.source || !conn.target) return;
      addBusinessRelationship(conn.source, conn.target, "one_to_many");
    },
    [addBusinessRelationship]
  );

  const onNodeClick: NodeMouseHandler = useCallback((_evt, node) => {
    setSelectedRelationship(null);
    setSelectedTable(node.id);
  }, []);

  const onEdgeClick: EdgeMouseHandler = useCallback((_evt, edge) => {
    setSelectedTable(null);
    setSelectedRelationship(edge.id);
  }, []);

  const onNodeDragStop: NodeMouseHandler = useCallback(
    (_evt, node) => {
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
    },
    [updateDraft]
  );

  const applyIntent = useCallback(
    async (forcedIntent?: string) => {
      if (!draft) return;
      const text = (forcedIntent ?? intentText).trim();
      if (!text) {
        setStatus("Describe what data your app needs first.");
        return;
      }

      setAskingAi(true);
      setError(null);
      try {
        const res = await dbSchemaIntent(projectId, {
          base_version: schemaVersion,
          draft,
          intent_text: text,
        });
        setDraft(cloneSchema(res.draft));
        setSchemaVersion(res.base_version || schemaVersion);
        setAssistantMessage(res.assistant_message || "Draft updated.");
        setChangeCards(Array.isArray(res.change_cards) ? res.change_cards : []);
        setNeedsClarification(Boolean(res.needs_clarification));
        setClarificationQuestion(res.clarification_question || "");
        setClarificationOptions(
          Array.isArray(res.clarification_options) ? res.clarification_options : []
        );
        setWarnings(Array.isArray(res.warnings) ? res.warnings : []);
        setStatus(res.needs_clarification ? "Need clarification" : "Draft updated with AI");
        setSelectedRelationship(null);
        setSelectedTable((prev) => {
          if (prev && res.draft.tables.some((t) => t.name === prev)) return prev;
          return res.draft.tables[0]?.name || null;
        });
      } catch (e: unknown) {
        const err = e as { status?: number; data?: unknown };
        const data = asRecord(err?.data);
        if (err?.status === 409 && data?.error === "version_conflict") {
          setStatus("Schema changed remotely; reloading.");
          await loadSchema();
          return;
        }
        setError(e instanceof Error ? e.message : "intent_failed");
      } finally {
        setAskingAi(false);
      }
    },
    [draft, intentText, loadSchema, projectId, schemaVersion]
  );

  const runTechnicalReview = useCallback(async () => {
    if (!draft) return;
    setReviewingTech(true);
    setError(null);
    try {
      const res = await dbSchemaReview(projectId, { base_version: schemaVersion, draft });
      setTechnicalReviewText(res.review?.summary || "");
      setWarnings(res.warnings || []);
      setSqlPreview(res.sql_preview || []);
      setStatus("Technical review refreshed");
    } catch (e: unknown) {
      const err = e as { status?: number; data?: unknown };
      if (err?.status === 409) {
        setStatus("Schema changed remotely; reloading.");
        await loadSchema();
        return;
      }
      setError(e instanceof Error ? e.message : "review_failed");
    } finally {
      setReviewingTech(false);
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
        if (err?.status === 409 && data?.error === "destructive_confirmation_required") {
          const review = asRecord(data.review);
          const summary =
            typeof review?.summary === "string" && review.summary.trim()
              ? review.summary.trim()
              : "This change may remove data.";
          const details = Array.isArray(data.destructive_details)
            ? data.destructive_details.map((x) => String(x)).join("\n")
            : "Potential destructive changes.";
          const ok = window.confirm(
            `${summary}\n\n${details}\n\nProceed with apply?`
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
      setWarnings(res.warnings || []);
      setChangeCards([]);
      setNeedsClarification(false);
      setClarificationQuestion("");
      setClarificationOptions([]);
      setSqlPreview(res.sql_preview || []);
      setTechnicalReviewText("");
      setLastApplied(new Date().toLocaleString());
      const sha = res.git_sync?.commit_sha;
      setAssistantMessage(
        sha
          ? `Applied. Your project was synced (${String(sha).slice(0, 8)}).`
          : "Applied successfully."
      );
      setStatus("Changes applied");
      setSelectedRelationship(null);
      setSelectedTable(res.schema.tables[0]?.name || null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "apply_failed");
    } finally {
      setApplying(false);
    }
  }, [draft, projectId, schemaVersion]);

  if (loading || !draft) {
    return <div style={{ padding: 16 }}>Loading database workspace...</div>;
  }

  const otherTables = draft.tables.filter((t) => t.name !== selectedTableObj?.name);

  return (
    <div className="flex flex-col h-full min-h-0 bg-card">
      <div className="border-b px-3 py-2 flex items-center gap-3">
        <div className="text-sm font-semibold">Database</div>
        <div className="text-xs text-muted-foreground">{status || "Ready"}</div>
        <div className="text-xs text-muted-foreground">Last applied: {lastApplied || "Not yet"}</div>
        <div className="ml-auto flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => void loadSchema()}>
            Reload
          </Button>
          <Button
            size="sm"
            variant={advancedOpen ? "secondary" : "outline"}
            onClick={() => setAdvancedOpen((v) => !v)}
          >
            {advancedOpen ? "Hide advanced" : "Advanced settings"}
          </Button>
        </div>
      </div>

      <div className="border-b px-3 py-3 bg-emerald-50/60">
        <div className="text-xs font-semibold mb-2">Describe the data your app needs</div>
        <div className="grid grid-cols-[1fr_auto_auto] gap-2 items-start">
          <Textarea
            value={intentText}
            onChange={(e) => setIntentText(e.target.value)}
            placeholder="Example: I need customers, orders, and each order should belong to a customer."
            className="min-h-[72px] bg-white"
          />
          <Button size="sm" onClick={() => void applyIntent()} disabled={askingAi || !intentText.trim()}>
            {askingAi ? "Thinking..." : "Ask AI"}
          </Button>
          <Button size="sm" onClick={() => void runApply()} disabled={applying}>
            {applying ? "Applying..." : "Apply"}
          </Button>
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {SUGGESTED_INTENTS.map((chip) => (
            <Button
              key={chip}
              size="sm"
              variant="outline"
              onClick={() => {
                setIntentText(chip);
                void applyIntent(chip);
              }}
              disabled={askingAi}
            >
              {chip}
            </Button>
          ))}
        </div>
      </div>

      {error ? (
        <div className="border-b px-3 py-2 text-sm text-red-700 bg-red-50">Error: {error}</div>
      ) : null}

      {assistantMessage || changeCards.length ? (
        <div className="border-b px-3 py-3 bg-white">
          {assistantMessage ? <div className="text-sm mb-2">{assistantMessage}</div> : null}
          {needsClarification && clarificationQuestion ? (
            <div className="mb-2 text-sm text-amber-800 bg-amber-50 border rounded px-2 py-1">
              {clarificationQuestion}
            </div>
          ) : null}
          {needsClarification && clarificationOptions.length ? (
            <div className="mb-2 flex flex-wrap gap-2">
              {clarificationOptions.map((opt) => (
                <Button
                  key={opt.id || opt.label}
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setIntentText(opt.label);
                    void applyIntent(opt.label);
                  }}
                >
                  {opt.label}
                </Button>
              ))}
            </div>
          ) : null}
          {changeCards.length ? (
            <div className="grid md:grid-cols-2 gap-2">
              {changeCards.map((card) => (
                <div key={card.id} className="border rounded p-2 bg-slate-50">
                  <div className="text-xs font-semibold">{card.title}</div>
                  <div className="text-xs text-muted-foreground">{card.description}</div>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="flex-1 min-h-0 grid [grid-template-columns:260px_1fr_360px]">
        <div className="border-r p-3 min-h-0 overflow-auto">
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search tables"
          />

          <div className="border rounded p-2 mt-3 bg-blue-50">
            <div className="text-xs font-semibold mb-1">
              {draft.tables.length ? "Create another table" : "Create your first table"}
            </div>
            <div className="text-[11px] text-muted-foreground mb-2">
              Use a friendly name. We handle the technical parts.
            </div>
            <div className="flex gap-2">
              <Input
                value={newTableLabel}
                onChange={(e) => setNewTableLabel(e.target.value)}
                placeholder="e.g. Customers"
              />
              <Button size="sm" onClick={() => addTable(newTableLabel)} disabled={!newTableLabel.trim()}>
                Create
              </Button>
            </div>
          </div>

          {!draft.tables.length ? (
            <div className="border rounded p-2 mt-3 bg-emerald-50">
              <div className="text-xs font-semibold mb-1">Quick walkthrough</div>
              <ol className="text-[11px] list-decimal pl-4 space-y-1">
                <li>Describe your data in the AI box above.</li>
                <li>Review the visual tables and links.</li>
                <li>Click Apply to update your app database.</li>
              </ol>
            </div>
          ) : null}

          <div className="space-y-2 mt-3">
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
                }}
              >
                <div className="text-sm font-medium">{t.label}</div>
                <div className="text-xs text-muted-foreground">{t.columns.length} fields</div>
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

          {warnings.length ? (
            <div className="mt-4 border rounded p-2 text-xs bg-amber-50">
              <div className="font-semibold mb-1">Notes</div>
              <ul className="list-disc pl-4">
                {warnings.map((w, idx) => (
                  <li key={`w-${idx}`}>{w}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>

        <div className="min-h-0">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            onEdgeClick={onEdgeClick}
            onNodeDragStop={onNodeDragStop}
            onPaneClick={() => {
              setSelectedRelationship(null);
            }}
          >
            <Background gap={20} size={1} />
            <Controls />
          </ReactFlow>
        </div>

        <div className="border-l p-3 min-h-0 overflow-auto">
          {selectedRelationshipObj ? (
            <div className="space-y-3">
              <div className="text-sm font-semibold">Relationship</div>
              <div className="text-xs text-muted-foreground">
                {relationSentence(draft, selectedRelationshipObj)}
              </div>
              <Button
                variant="destructive"
                onClick={() => {
                  const ok = window.confirm("Delete this relationship from the draft?");
                  if (!ok) return;
                  updateDraft((prev) => {
                    prev.relationships = prev.relationships.filter(
                      (r) => r.name !== selectedRelationshipObj.name
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
                Friendly name
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

              <div className="border rounded p-2 space-y-2">
                <div className="text-xs font-semibold">Fields</div>
                {selectedTableObj.columns.map((c) => (
                  <div key={`${selectedTableObj.name}:${c.name}`} className="border rounded p-2 bg-slate-50">
                    <div className="flex gap-2 items-start">
                      <div className="flex-1">
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
                        <div className="text-[11px] text-muted-foreground mt-1">
                          {presetByKey.get(inferPreset(c))?.label || "Custom"}
                        </div>
                      </div>
                      <Button
                        size="sm"
                        variant="destructive"
                        disabled={Boolean(c.is_primary)}
                        onClick={() => deleteField(c.name)}
                      >
                        Delete
                      </Button>
                    </div>
                  </div>
                ))}

                <div className="border rounded p-2 bg-white">
                  <div className="text-xs font-semibold mb-2">Add field</div>
                  <div className="grid grid-cols-2 gap-2">
                    <Input
                      placeholder="Field name"
                      value={newFieldLabel}
                      onChange={(e) => setNewFieldLabel(e.target.value)}
                    />
                    <select
                      className="border rounded px-2 py-1 text-sm"
                      value={newFieldPreset}
                      onChange={(e) => setNewFieldPreset(e.target.value as FieldPresetKey)}
                    >
                      {FIELD_PRESETS.map((preset) => (
                        <option key={preset.key} value={preset.key}>
                          {preset.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <Button className="mt-2" size="sm" onClick={addField}>
                    Add field
                  </Button>
                </div>
              </div>

              <div className="border rounded p-2 space-y-2">
                <div className="text-xs font-semibold">Link this table</div>
                <label className="text-xs block">
                  Target table
                  <select
                    className="mt-1 w-full border rounded px-2 py-1 text-sm"
                    value={relationTargetTable}
                    onChange={(e) => setRelationTargetTable(e.target.value)}
                  >
                    <option value="">Select table</option>
                    {otherTables.map((t) => (
                      <option key={`target-${t.name}`} value={t.name}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="text-xs block">
                  Relationship type
                  <select
                    className="mt-1 w-full border rounded px-2 py-1 text-sm"
                    value={relationKind}
                    onChange={(e) => setRelationKind(e.target.value as RelationKind)}
                  >
                    {RELATION_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                  <div className="mt-1 text-[11px] text-muted-foreground">
                    {RELATION_OPTIONS.find((x) => x.value === relationKind)?.helper}
                  </div>
                </label>
                <Button
                  size="sm"
                  disabled={!relationTargetTable}
                  onClick={() =>
                    addBusinessRelationship(selectedTableObj.name, relationTargetTable, relationKind)
                  }
                >
                  Add relationship
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-2 text-sm text-muted-foreground">
              <div>Select a table or relationship from the diagram.</div>
              <div className="text-xs">Tip: Start with the AI intent box to generate your first draft.</div>
            </div>
          )}

          {advancedOpen ? (
            <div className="mt-4 border-t pt-3 space-y-3">
              <div className="text-xs font-semibold">Advanced settings</div>
              <div className="text-[11px] text-muted-foreground">
                Schema version: <span className="font-mono">{schemaVersion || "-"}</span>
              </div>

              {selectedRelationshipObj ? (
                <div className="border rounded p-2">
                  <div className="text-xs font-semibold mb-2">Relationship rules</div>
                  <label className="text-xs block">
                    On delete
                    <select
                      className="mt-1 w-full border rounded px-2 py-1 text-sm"
                      value={selectedRelationshipObj.on_delete || "NO ACTION"}
                      onChange={(e) => {
                        const next = e.target.value;
                        updateDraft((prev) => {
                          const rel = prev.relationships.find((r) => r.name === selectedRelationshipObj.name);
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
                  <label className="text-xs block mt-2">
                    On update
                    <select
                      className="mt-1 w-full border rounded px-2 py-1 text-sm"
                      value={selectedRelationshipObj.on_update || "NO ACTION"}
                      onChange={(e) => {
                        const next = e.target.value;
                        updateDraft((prev) => {
                          const rel = prev.relationships.find((r) => r.name === selectedRelationshipObj.name);
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
                </div>
              ) : null}

              {selectedTableObj ? (
                <div className="border rounded p-2">
                  <div className="text-xs font-semibold mb-2">Technical fields</div>
                  <div className="text-[11px] text-muted-foreground mb-2">
                    Table key: <span className="font-mono">{selectedTableObj.name}</span>
                  </div>
                  <div className="space-y-2">
                    {selectedTableObj.columns.map((c) => (
                      <div key={`adv-${selectedTableObj.name}-${c.name}`} className="border rounded p-2 bg-slate-50">
                        <div className="text-[11px] font-mono mb-1">{c.name}</div>
                        <div className="grid grid-cols-2 gap-2">
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
                              }}
                            >
                              {TYPE_OPTIONS.map((opt) => (
                                <option key={`adv-type-${opt.value}`} value={opt.value}>
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
                              checked={Boolean(c.nullable)}
                              disabled={Boolean(c.is_primary)}
                              onChange={(e) => {
                                const next = e.target.checked;
                                updateDraft((prev) => {
                                  const t = prev.tables.find((x) => x.name === selectedTableObj.name);
                                  const col = t?.columns.find((x) => x.name === c.name);
                                  if (col) col.nullable = next;
                                  return prev;
                                });
                              }}
                            />
                          </label>
                          <label className="text-xs block col-span-2">
                            Default
                            <Input
                              value={formatDefaultValue(c.default)}
                              placeholder="Optional"
                              onChange={(e) => {
                                const next = parseDefaultValue(c.type, e.target.value);
                                updateDraft((prev) => {
                                  const t = prev.tables.find((x) => x.name === selectedTableObj.name);
                                  const col = t?.columns.find((x) => x.name === c.name);
                                  if (col) col.default = next;
                                  return prev;
                                });
                              }}
                            />
                          </label>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              <div className="border rounded p-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-xs font-semibold">Technical review</div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => void runTechnicalReview()}
                    disabled={reviewingTech}
                  >
                    {reviewingTech ? "Refreshing..." : "Refresh review"}
                  </Button>
                </div>
                <div className="text-xs whitespace-pre-wrap mt-2">
                  {technicalReviewText || "No technical review yet."}
                </div>
                <details className="mt-2 border rounded p-2">
                  <summary className="text-xs font-semibold cursor-pointer">SQL preview</summary>
                  <pre className="mt-2 text-[11px] whitespace-pre-wrap max-h-[220px] overflow-auto">
                    {(sqlPreview || []).join("\n") || "No SQL preview available."}
                  </pre>
                </details>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
};
