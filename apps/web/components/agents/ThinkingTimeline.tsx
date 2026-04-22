"use client";

import { motion } from "motion/react";
import { Brain, CheckCircle, Circle } from "lucide-react";

interface ThinkingStep {
  id: string;
  thought: string;
  iteration?: number;
  timestamp?: string;
}

export function ThinkingTimeline({ steps }: { steps: ThinkingStep[] }) {
  if (steps.length === 0) return null;

  return (
    <div className="relative pl-6 space-y-4">
      {/* Vertical line */}
      <div className="absolute left-[9px] top-2 bottom-2 w-px bg-border" />

      {steps.map((step, i) => {
        const isLast = i === steps.length - 1;
        return (
          <motion.div
            key={step.id}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.05 }}
            className="relative"
          >
            {/* Dot */}
            <div className="absolute -left-6 top-0.5">
              {isLast ? (
                <motion.div
                  animate={{ scale: [1, 1.2, 1] }}
                  transition={{ repeat: Infinity, duration: 2 }}
                >
                  <Circle className="h-4 w-4 fill-blue-500 text-blue-500" />
                </motion.div>
              ) : (
                <CheckCircle className="h-4 w-4 text-muted-foreground" />
              )}
            </div>

            <div className="rounded-md border bg-muted/30 p-3 text-sm space-y-1">
              {step.iteration && (
                <div className="text-xs font-medium text-blue-600">
                  Iteration {step.iteration}
                </div>
              )}
              <div className="text-muted-foreground leading-relaxed">
                {step.thought}
              </div>
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}
