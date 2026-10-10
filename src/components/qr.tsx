import QRCode from "qrcode";
import { cn } from "@/lib/cn";

/** Server-rendered QR code as inline SVG. Uses currentColor so it follows the theme. */
export async function Qr({ value, className, label }: { value: string; className?: string; label: string }) {
  const svg = await QRCode.toString(value, { type: "svg", margin: 0, errorCorrectionLevel: "M", color: { dark: "#000000", light: "#0000" } });
  return (
    <div
      role="img"
      aria-label={label}
      className={cn("aspect-square [&>svg]:size-full [&_path[stroke]]:stroke-current [&_path:first-child]:fill-transparent", className)}
      dangerouslySetInnerHTML={{ __html: svg.replace(/stroke="#000000"/g, 'stroke="currentColor"') }}
    />
  );
}
