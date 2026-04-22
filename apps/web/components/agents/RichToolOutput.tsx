"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import {
  ExternalLink,
  ImageIcon,
  Ticket,
  Tag,
  Search,
  Globe,
  MousePointerClick,
  Music,
  Calendar,
  MapPin,
  Users,
} from "lucide-react";
import { ImageLightbox } from "./ImageLightbox";

function SafeJson(value: unknown): any {
  if (typeof value === "string") {
    try {
      return JSON.parse(value);
    } catch {
      return value;
    }
  }
  return value;
}

function ImagePreview({ url, caption }: { url: string; caption?: string }) {
  const [error, setError] = useState(false);
  if (error) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="block rounded-md border bg-muted/30 p-2 text-xs text-blue-600 hover:underline truncate"
      >
        <ImageIcon className="inline h-3 w-3 mr-1" />
        {caption || url}
      </a>
    );
  }
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="block rounded-md border overflow-hidden hover:opacity-90 transition-opacity"
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={url}
        alt={caption || "Image"}
        className="w-full h-32 object-cover"
        onError={() => setError(true)}
        loading="lazy"
      />
      {caption && (
        <div className="px-2 py-1 text-xs text-muted-foreground truncate bg-muted/30">
          {caption}
        </div>
      )}
    </a>
  );
}

function UrlCard({
  url,
  title,
  icon: Icon = Globe,
}: {
  url: string;
  title?: string;
  icon?: React.ComponentType<{ className?: string }>;
}) {
  const domain = (() => {
    try {
      return new URL(url).hostname.replace(/^www\./, "");
    } catch {
      return url;
    }
  })();
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-center gap-3 rounded-lg border p-3 hover:bg-muted/50 transition-colors"
    >
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-blue-50 text-blue-600 dark:bg-blue-950">
        <Icon className="h-5 w-5" />
      </div>
      <div className="min-w-0">
        <div className="text-sm font-medium text-blue-600 truncate">
          {title || domain}
        </div>
        <div className="text-xs text-muted-foreground truncate">{domain}</div>
      </div>
      <ExternalLink className="ml-auto h-4 w-4 shrink-0 text-muted-foreground" />
    </a>
  );
}

export function RichToolOutput({
  toolName,
  output,
}: {
  toolName: string;
  output: unknown;
}) {
  const data = SafeJson(output);

  if (toolName === "navigate") {
    const url =
      typeof data === "string"
        ? data.match(/https?:\/\/[^\s]+/)?.[0]
        : data?.url || "";
    if (!url) return null;
    return (
      <div className="space-y-2">
        <UrlCard url={url} title={data?.title || url} icon={Globe} />
      </div>
    );
  }

  if (toolName === "click_link") {
    const url = data?.new_url || "";
    if (!url) return null;
    return (
      <div className="space-y-2">
        <UrlCard url={url} title="Clicked link" icon={MousePointerClick} />
      </div>
    );
  }

  if (toolName === "extract_data") {
    const d = typeof data === "object" ? data : {};
    return (
      <div className="rounded-lg border bg-card p-4 space-y-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-card-foreground">
          <Calendar className="h-4 w-4 text-blue-500" />
          Extracted Festival Data
        </div>
        <div className="grid gap-2 text-sm">
          {d.name && (
            <div className="flex items-start gap-2">
              <span className="text-muted-foreground shrink-0">Name:</span>
              <span className="font-medium">{d.name}</span>
            </div>
          )}
          {d.start_date && (
            <div className="flex items-start gap-2">
              <MapPin className="h-3.5 w-3.5 text-muted-foreground shrink-0 mt-0.5" />
              <span>{d.start_date}</span>
            </div>
          )}
          {d.location && (
            <div className="flex items-start gap-2">
              <MapPin className="h-3.5 w-3.5 text-muted-foreground shrink-0 mt-0.5" />
              <span>{d.location}</span>
            </div>
          )}
          {d.artists && Array.isArray(d.artists) && d.artists.length > 0 && (
            <div className="flex items-start gap-2">
              <Users className="h-3.5 w-3.5 text-muted-foreground shrink-0 mt-0.5" />
              <span>{d.artists.length} artists</span>
            </div>
          )}
        </div>
      </div>
    );
  }

  if (toolName === "screenshot_lineup") {
    const artists = Array.isArray(data?.artists) ? data.artists : [];
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Music className="h-4 w-4 text-purple-500" />
          {artists.length} artists found from screenshot
        </div>
        {artists.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {artists.slice(0, 30).map((artist: string, i: number) => (
              <Badge key={i} variant="secondary" className="text-xs font-normal">
                {artist}
              </Badge>
            ))}
            {artists.length > 30 && (
              <Badge variant="outline" className="text-xs">
                +{artists.length - 30} more
              </Badge>
            )}
          </div>
        )}
      </div>
    );
  }

  if (toolName === "search_alternatives") {
    const results = Array.isArray(data?.results) ? data.results : [];
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Search className="h-4 w-4 text-green-500" />
          {results.length} alternative sources
        </div>
        <div className="space-y-2">
          {results.map((r: any, i: number) => (
            <UrlCard key={i} url={r.url} title={r.title} icon={Search} />
          ))}
        </div>
      </div>
    );
  }

  if (toolName === "select_tags") {
    const tags = Array.isArray(data?.tags) ? data.tags : [];
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Tag className="h-4 w-4 text-orange-500" />
          {tags.length} tags selected
        </div>
        <div className="flex flex-wrap gap-1.5">
          {tags.map((tag: string, i: number) => (
            <Badge key={i} variant="secondary" className="text-xs font-normal">
              {tag}
            </Badge>
          ))}
        </div>
      </div>
    );
  }

  if (toolName === "search_youtube") {
    const url = data?.youtube_url;
    return (
      <div className="space-y-2">
        {url ? (
          <UrlCard url={url} title={data.title || "YouTube video"} icon={Globe} />
        ) : (
          <p className="text-sm text-muted-foreground">No video found</p>
        )}
      </div>
    );
  }

  if (toolName === "select_media") {
    const logo = data?.logo?.url;
    const gallery = Array.isArray(data?.gallery) ? data.gallery : [];
    const lineup = Array.isArray(data?.lineup) ? data.lineup : [];

    const allImages = [
      ...(logo ? [{ url: logo, caption: "Logo" }] : []),
      ...gallery.map((item: any) => ({
        url: item.url,
        caption: item.caption || "Gallery",
      })),
      ...lineup.map((url: string) => ({ url, caption: "Lineup" })),
    ];

    const [lightboxOpen, setLightboxOpen] = useState(false);
    const [lightboxIndex, setLightboxIndex] = useState(0);

    const openLightbox = (index: number) => {
      setLightboxIndex(index);
      setLightboxOpen(true);
    };

    return (
      <div className="space-y-4">
        {allImages.length > 0 && (
          <ImageLightbox
            images={allImages}
            initialIndex={lightboxIndex}
            open={lightboxOpen}
            onOpenChange={setLightboxOpen}
          />
        )}

        {logo && (
          <div>
            <div className="text-sm font-medium mb-2">Logo</div>
            <button onClick={() => openLightbox(0)} className="w-full text-left">
              <ImagePreview url={logo} caption="Selected logo" />
            </button>
          </div>
        )}
        {gallery.length > 0 && (
          <div>
            <div className="text-sm font-medium mb-2">
              Gallery ({gallery.length})
            </div>
            <div className="grid grid-cols-2 gap-2">
              {gallery.slice(0, 4).map((item: any, i: number) => (
                <button
                  key={i}
                  onClick={() => openLightbox(logo ? 1 + i : i)}
                  className="w-full text-left"
                >
                  <ImagePreview url={item.url} caption={item.caption} />
                </button>
              ))}
            </div>
            {gallery.length > 4 && (
              <p className="text-xs text-muted-foreground mt-1">
                +{gallery.length - 4} more
              </p>
            )}
          </div>
        )}
        {lineup.length > 0 && (
          <div>
            <div className="text-sm font-medium mb-2">
              Lineup images ({lineup.length})
            </div>
            <div className="grid grid-cols-2 gap-2">
              {lineup.slice(0, 4).map((url: string, i: number) => (
                <button
                  key={i}
                  onClick={() =>
                    openLightbox(
                      (logo ? 1 : 0) + gallery.length + i
                    )
                  }
                  className="w-full text-left"
                >
                  <ImagePreview key={i} url={url} />
                </button>
              ))}
            </div>
            {lineup.length > 4 && (
              <p className="text-xs text-muted-foreground mt-1">
                +{lineup.length - 4} more
              </p>
            )}
          </div>
        )}
      </div>
    );
  }

  if (toolName === "extract_tickets") {
    const tickets = Array.isArray(data?.tickets) ? data.tickets : [];
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Ticket className="h-4 w-4 text-red-500" />
          {tickets.length} ticket types
        </div>
        {tickets.length > 0 && (
          <div className="rounded-md border">
            <div className="grid grid-cols-3 gap-2 border-b bg-muted/50 px-3 py-1.5 text-xs font-medium text-muted-foreground">
              <div>Type</div>
              <div>Price</div>
              <div>Currency</div>
            </div>
            {tickets.map((t: any, i: number) => (
              <div
                key={i}
                className="grid grid-cols-3 gap-2 border-b px-3 py-1.5 text-xs last:border-b-0"
              >
                <div>{t.description || "Ticket"}</div>
                <div>{t.price_min || t.price || "-"}</div>
                <div>{t.price_currency_code || "-"}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  return null;
}
