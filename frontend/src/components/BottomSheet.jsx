import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence, useDragControls } from 'framer-motion';
import ConfirmDialog from './ConfirmDialog';
import ModalBackdrop from './modal/ModalBackdrop';
import SealCloseButton from './modal/SealCloseButton';
import SealPulseRing from './modal/SealPulseRing';
import useVisualViewportInset from './modal/useVisualViewportInset';
import { registerSheetHistory } from './modal/sheetHistory';
import useIsDesktop from '../hooks/useIsDesktop';
import useModalFocus from './modal/useModalFocus';

// Shared modal shell for every form dialog in the app. Dual-mode under the
// "Sheikah Stamp" DNA:
//   Desktop (md+)   — centered parchment card with stamp-in motion (max-w-lg).
//   Mobile          — bottom-sheet slide (thumb-reach), sheikah-glyph drag
//                     handle, one-shot teal halo across the top edge,
//                     parchment texture carried through.
