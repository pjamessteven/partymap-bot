"use client";

import { useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Calendar,
  MapPin,
  Users,
  Globe,
  Music,
  Ticket,
  ImageIcon,
  Tag,
} from "lucide-react";
import { TagList } from "./TagBadge";

interface FestivalProfileData {
  name?: string;
  description?: string;
  url?: string;
  logo?: string;
  date_time?: { start?: string; end?: string };
  location?: string;
  artists?: string[];
  tags?: string[];
  tickets?: Array<{
    description?: string;
    price_min?: number;
    price_currency_code?: string;
  }>;
  media?: {
    gallery?: Array<{ url: string; caption?: string }>;
    lineup?: string[];
  };
}

function extractDataFromEvents(events: Array<{ type: string; data: unknown }>): FestivalProfileData {
  const profile: FestivalProfileData = {};

  for (const evt of events) {
    if (evt.type === "tool_progress") {
      const data = evt.data as {
        tool_name?: string;
        data?: Record<string, unknown>;
      };
      const toolData = data.data || {};

      switch (data.tool_name) {
        case "extract_data":
          if (toolData.name) profile.name = toolData.name as string;
          if (toolData.start_date) {
            profile.date_time = {
              ...profile.date_time,
              start: toolData.start_date as string,
            };
          }
          if (toolData.location) profile.location = toolData.location as string;
          if (toolData.artists) profile.artists = toolData.artists as string[];
          break;
        case "select_tags":
          if (toolData.tags) profile.tags = toolData.tags as string[];
          break;
        case "select_media":
          profile.media = {
            gallery: (toolData.gallery || []) as Array<{ url: string; caption?: string }>,
            lineup: (toolData.lineup || []) as string[],
          };
          if ((toolData as any).logo?.url) {
            profile.logo = (toolData as any).logo.url;
          }
          break;
        case "extract_tickets":
          if (toolData.tickets) profile.tickets = toolData.tickets as any[];
          break;
        case "search_youtube":
          // Not showing in profile, but could add video link
          break;
      }
    }
  }

  return profile;
}

export function FestivalProfileCard({
  events,
}: {
  events: Array<{ type: string; data: unknown }>;
}) {
  const profile = useMemo(() => extractDataFromEvents(events), [events]);

  if (
    !profile.name &&
    !profile.location &&
    !profile.date_time &&
    !profile.tags &&
    !profile.artists
  ) {
    return null;
  }

  return (
    <Card className="border-blue-200 bg-blue-50/50 dark:border-blue-900 dark:bg-blue-950/30">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <Globe className="h-4 w-4 text-blue-500" />
          Festival Profile
          {profile.name && (
            <span className="text-muted-foreground font-normal">
              — {profile.name}
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Core info grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 text-sm">
          {profile.date_time?.start && (
            <div className="flex items-center gap-2">
              <Calendar className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
              <span>{profile.date_time.start}</span>
            </div>
          )}
          {profile.location && (
            <div className="flex items-center gap-2">
              <MapPin className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
              <span className="truncate">{profile.location}</span>
            </div>
          )}
          {profile.artists && profile.artists.length > 0 && (
            <div className="flex items-center gap-2">
              <Users className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
              <span>{profile.artists.length} artists</span>
            </div>
          )}
          {profile.tickets && profile.tickets.length > 0 && (
            <div className="flex items-center gap-2">
              <Ticket className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
              <span>{profile.tickets.length} ticket types</span>
            </div>
          )}
        </div>

        {/* Tags */}
        {profile.tags && profile.tags.length > 0 && (
          <div className="flex items-start gap-2">
            <Tag className="h-3.5 w-3.5 text-muted-foreground shrink-0 mt-0.5" />
            <TagList tags={profile.tags} />
          </div>
        )}

        {/* Media preview */}
        {profile.logo && (
          <div className="flex items-center gap-2 text-sm">
            <ImageIcon className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            <a
              href={profile.logo}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:underline truncate"
            >
              Logo
            </a>
          </div>
        )}
        {profile.media &&
          (profile.media.gallery?.length || 0) + (profile.media.lineup?.length || 0) > 0 && (
            <div className="flex items-center gap-2 text-sm">
              <ImageIcon className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
              <span className="text-muted-foreground">
                {(profile.media.gallery?.length || 0) + (profile.media.lineup?.length || 0)}{" "}
                images
              </span>
            </div>
          )}
      </CardContent>
    </Card>
  );
}
