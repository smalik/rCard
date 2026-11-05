"use client";

import {
  closestCenter,
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { ChevronDown, ChevronUp, GripVertical } from "lucide-react";
import { type ReactNode, useId } from "react";

import { move } from "@/lib/library";
import { cn } from "@/lib/utils";

type Props<T> = {
  items: T[];
  id: (item: T) => string;
  // What a screen reader calls each item while it moves.
  name: (item: T) => string;
  // Shows handles and up and down buttons.
  arranging: boolean;
  onReorder: (next: T[]) => void;
  // Draws an item. While arranging with inline controls, `controls` holds the
  // handle and arrows for the item to place in its own top line.
  render: (item: T, index: number, controls: ReactNode) => ReactNode;
  label: string;
  // "side" puts the handle left and the arrows right of each item; "inline"
  // hands them to render, for tall items whose top line should carry them.
  controls?: "side" | "inline";
  className?: string;
};

/** A vertical list the person can rearrange: drag by the handle (mouse,
 * touch, or keyboard with space and the arrows), or use the up and down
 * buttons. */
export function SortableList<T>({
  items,
  id,
  name,
  arranging,
  onReorder,
  render,
  label,
  controls = "side",
  className,
}: Props<T>) {
  const contextId = useId();
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 120, tolerance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const ids = items.map(id);
  const nameOf = (key: string | number) => {
    const item = items.find((i) => id(i) === String(key));
    return item ? name(item) : "item";
  };

  function onDragEnd({ active, over }: DragEndEvent) {
    if (!over || active.id === over.id) return;
    onReorder(move(items, ids.indexOf(String(active.id)), ids.indexOf(String(over.id))));
  }

  if (!arranging) {
    return (
      <ol aria-label={label} className={className}>
        {items.map((item, index) => (
          <li key={id(item)}>{render(item, index, null)}</li>
        ))}
      </ol>
    );
  }

  return (
    <DndContext
      id={contextId}
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragEnd={onDragEnd}
      accessibility={{
        announcements: {
          onDragStart: ({ active }) => `Picked up ${nameOf(active.id)}.`,
          onDragOver: ({ active, over }) =>
            over ? `${nameOf(active.id)} is now at place ${ids.indexOf(String(over.id)) + 1}.` : "",
          onDragEnd: ({ active, over }) =>
            over
              ? `${nameOf(active.id)} dropped at place ${ids.indexOf(String(over.id)) + 1}.`
              : `${nameOf(active.id)} dropped.`,
          onDragCancel: ({ active }) => `Moving ${nameOf(active.id)} was cancelled.`,
        },
      }}
    >
      <SortableContext items={ids} strategy={verticalListSortingStrategy}>
        <ol aria-label={`${label}, rearranging`} className={className}>
          {items.map((item, index) => (
            <SortableRow
              key={id(item)}
              id={id(item)}
              name={name(item)}
              first={index === 0}
              last={index === items.length - 1}
              onUp={() => onReorder(move(items, index, index - 1))}
              onDown={() => onReorder(move(items, index, index + 1))}
              inline={controls === "inline"}
            >
              {(handles) => render(item, index, handles)}
            </SortableRow>
          ))}
        </ol>
      </SortableContext>
    </DndContext>
  );
}

const ARROW =
  "grid size-7 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-30 focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none";

function SortableRow({
  id,
  name,
  first,
  last,
  onUp,
  onDown,
  inline,
  children,
}: {
  id: string;
  name: string;
  first: boolean;
  last: boolean;
  onUp: () => void;
  onDown: () => void;
  inline: boolean;
  children: (controls: ReactNode) => ReactNode;
}) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } =
    useSortable({ id });
  const handle = (
    <button
      ref={setActivatorNodeRef}
      type="button"
      aria-label={`Move ${name}`}
      className={cn(
        "flex shrink-0 cursor-grab touch-none items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none active:cursor-grabbing",
        inline ? "size-7" : "w-6",
      )}
      {...attributes}
      {...listeners}
    >
      <GripVertical className="size-4" />
    </button>
  );
  const arrows = (
    <>
      <button type="button" disabled={first} onClick={onUp} aria-label={`Move ${name} up`} className={ARROW}>
        <ChevronUp className="size-4" />
      </button>
      <button type="button" disabled={last} onClick={onDown} aria-label={`Move ${name} down`} className={ARROW}>
        <ChevronDown className="size-4" />
      </button>
    </>
  );
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Translate.toString(transform), transition }}
      className={cn(
        "group/row relative rounded-xl",
        !inline && "flex items-stretch gap-1.5",
        isDragging && "z-10 scale-[1.015] bg-card shadow-lift",
      )}
    >
      {inline ? (
        children(
          <span className="flex shrink-0 items-center gap-0.5">
            {arrows}
            {handle}
          </span>,
        )
      ) : (
        <>
          {handle}
          <div className="min-w-0 flex-1">{children(null)}</div>
          {/* With a mouse the arrows wait for the row to be pointed at or
              focused; on touch they stay in view. */}
          <div className="flex shrink-0 flex-col justify-center gap-0.5 transition-opacity sm:flex-row sm:items-center pointer-fine:opacity-0 pointer-fine:group-focus-within/row:opacity-100 pointer-fine:group-hover/row:opacity-100">
            {arrows}
          </div>
        </>
      )}
    </li>
  );
}
