import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => cleanup());

// jsdom does not implement scrolling; the shell scrolls to top on navigation.
window.scrollTo = (() => undefined) as typeof window.scrollTo;
Element.prototype.scrollTo = (() => undefined) as typeof Element.prototype.scrollTo;
