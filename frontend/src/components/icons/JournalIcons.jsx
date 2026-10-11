import { House, Sparkles, PawPrint, Coins, Map, BookHeart, Clock, PenLine, ScrollText, Egg } from 'lucide-react';

// Keep the chapter/action exports compatible while sharing Meadow's clear
// Lucide vocabulary with ChapterNav. Decorative icons inherit the cover ink.
const iconProps = ({ size = 20, ...props }) => ({ size, 'aria-hidden': true, ...props });

export function TodayIcon(props) { return <House {...iconProps(props)} />; }
export function QuestsIcon(props) { return <Sparkles {...iconProps(props)} />; }
export function BestiaryIcon(props) { return <PawPrint {...iconProps(props)} />; }
export function TreasuryIcon(props) { return <Coins {...iconProps(props)} />; }
export function AtlasIcon(props) { return <Map {...iconProps(props)} />; }
export function ChronicleIcon(props) { return <BookHeart {...iconProps(props)} />; }
export function ClockFabIcon({ size = 22, ...props }) { return <Clock {...iconProps({ size, ...props })} />; }
export function InkwellIcon(props) { return <PenLine {...iconProps(props)} />; }
export function ScrollIcon(props) { return <ScrollText {...iconProps(props)} />; }
export function EggIcon(props) { return <Egg {...iconProps(props)} />; }
export function CoinIcon(props) { return <Coins {...iconProps(props)} />; }
export function DragonIcon(props) { return <PawPrint {...iconProps(props)} />; }
