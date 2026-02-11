export type DbColumn = {
  name: string;
  label: string;
  type: string;
  nullable: boolean;
  is_primary?: boolean;
  default?: unknown;
};

export type DbTable = {
  name: string;
  label: string;
  position: { x: number; y: number };
  columns: DbColumn[];
};

export type DbRelationship = {
  name: string;
  from_table: string;
  from_column: string;
  to_table: string;
  to_column: string;
  on_delete?: string;
  on_update?: string;
};

export type DbSchema = {
  app_id?: string;
  schema_name: string;
  tables: DbTable[];
  relationships: DbRelationship[];
};

export type DbSchemaGetResponse = {
  schema: DbSchema;
  version: string;
  db_schema?: string;
  db_role?: string;
  template_id?: string;
};

export type CitizenChangeCard = {
  id: string;
  title: string;
  description: string;
  kind: string;
  risk: "low" | "medium" | "high";
};

export type ClarificationOption = {
  id: string;
  label: string;
};

export type DbSchemaIntentResponse = {
  base_version: string;
  draft: DbSchema;
  assistant_message: string;
  change_cards: CitizenChangeCard[];
  needs_clarification: boolean;
  clarification_question: string;
  clarification_options: ClarificationOption[];
  warnings: string[];
};

export type DbSchemaReviewResponse = {
  review: {
    summary: string;
    destructive: boolean;
    destructive_details: string[];
    warnings: string[];
  };
  operations: Array<Record<string, unknown>>;
  warnings: string[];
  destructive: boolean;
  destructive_details: string[];
  sql_preview: string[];
  base_version: string;
};

export type DbSchemaApplyResponse = {
  applied: boolean;
  new_version: string;
  version: string;
  schema: DbSchema;
  migration_files: string[];
  git_sync: {
    attempted?: boolean;
    pushed?: boolean;
    commit_sha?: string | null;
    diff_stat?: string;
    name_status?: string;
    error?: string;
    detail?: string;
  };
  warnings: string[];
  summary: Record<string, unknown>;
  operations: Array<Record<string, unknown>>;
  sql_preview: string[];
};
