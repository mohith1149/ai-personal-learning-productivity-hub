import { Check, Pencil, Trash2, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import {
  useCategories,
  useCreateCategory,
  useDeleteCategory,
  useUpdateCategory,
  type Category,
} from "../../api/tasks";
import { controlClass, FormError } from "../../components/forms";
import { Modal } from "../../components/Modal";
import { Button, Spinner, cx } from "../../components/ui";

function CategoryRow({ cat }: { cat: Category }) {
  const update = useUpdateCategory();
  const del = useDeleteCategory();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(cat.name);
  const [confirming, setConfirming] = useState(false);
  const error = (update.error ?? del.error)?.message;

  const save = (e: FormEvent) => {
    e.preventDefault();
    if (name.trim() && name.trim() !== cat.name)
      update.mutate({ id: cat.id, body: { name: name.trim() } }, { onSuccess: () => setEditing(false) });
    else setEditing(false);
  };

  return (
    <li className="py-2">
      <div className="flex items-center gap-2">
        <input
          type="color"
          aria-label={`Colour for ${cat.name}`}
          value={cat.color}
          onChange={(e) => update.mutate({ id: cat.id, body: { color: e.target.value } })}
          className="h-7 w-7 shrink-0 cursor-pointer rounded border-0 bg-transparent p-0"
        />
        {editing ? (
          <form onSubmit={save} className="flex flex-1 items-center gap-1">
            <input
              aria-label={`New name for ${cat.name}`}
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={80}
              className={cx(controlClass, "min-w-0 flex-1")}
              autoFocus
            />
            <button type="submit" aria-label="Save name" className="rounded-lg p-1.5 text-emerald-600 hover:bg-slate-100 dark:hover:bg-slate-800">
              <Check className="h-4 w-4" aria-hidden />
            </button>
            <button
              type="button"
              aria-label="Cancel rename"
              onClick={() => {
                setEditing(false);
                setName(cat.name);
              }}
              className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              <X className="h-4 w-4" aria-hidden />
            </button>
          </form>
        ) : (
          <>
            <span className="flex-1 truncate text-sm">{cat.name}</span>
            {cat.is_system ? (
              <span className="text-xs text-slate-400">built-in</span>
            ) : confirming ? (
              <span className="flex items-center gap-1 text-xs">
                Delete?
                <Button variant="danger" className="px-2 py-1 text-xs" loading={del.isPending} onClick={() => del.mutate(cat.id)}>
                  Yes
                </Button>
                <Button variant="secondary" className="px-2 py-1 text-xs" onClick={() => setConfirming(false)}>
                  No
                </Button>
              </span>
            ) : (
              <>
                <button
                  onClick={() => setEditing(true)}
                  aria-label={`Rename ${cat.name}`}
                  className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
                >
                  <Pencil className="h-4 w-4" aria-hidden />
                </button>
                <button
                  onClick={() => setConfirming(true)}
                  aria-label={`Delete category ${cat.name}`}
                  className="rounded-lg p-1.5 text-slate-500 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40"
                >
                  <Trash2 className="h-4 w-4" aria-hidden />
                </button>
              </>
            )}
          </>
        )}
      </div>
      {error && <p role="alert" className="mt-1 pl-9 text-xs text-red-600 dark:text-red-400">{error}</p>}
    </li>
  );
}

export function CategoryManager({ onClose }: { onClose: () => void }) {
  const cats = useCategories();
  const create = useCreateCategory();
  const [name, setName] = useState("");
  const [color, setColor] = useState("#6366f1");

  const add = (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    create.mutate({ name: name.trim(), color }, { onSuccess: () => setName("") });
  };

  return (
    <Modal title="Task categories" onClose={onClose}>
      <form onSubmit={add} className="flex items-center gap-2">
        <input
          type="color"
          aria-label="New category colour"
          value={color}
          onChange={(e) => setColor(e.target.value)}
          className="h-9 w-9 shrink-0 cursor-pointer rounded border-0 bg-transparent p-0"
        />
        <input
          aria-label="New category name"
          placeholder="New category, e.g. Study"
          value={name}
          maxLength={80}
          onChange={(e) => setName(e.target.value)}
          className={cx(controlClass, "min-w-0 flex-1")}
        />
        <Button type="submit" loading={create.isPending} disabled={!name.trim()}>
          Add
        </Button>
      </form>
      <div className="mt-2">
        <FormError message={create.error?.message} />
      </div>

      {cats.isPending ? (
        <Spinner />
      ) : cats.data && cats.data.length > 0 ? (
        <ul className="mt-3 divide-y divide-slate-100 dark:divide-slate-800">
          {cats.data.map((c) => (
            <CategoryRow key={c.id} cat={c} />
          ))}
        </ul>
      ) : (
        <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">No categories yet. Add one above.</p>
      )}
      <p className="mt-4 text-xs text-slate-500 dark:text-slate-400">
        Deleting a category never deletes tasks. They just lose their category.
      </p>
    </Modal>
  );
}
