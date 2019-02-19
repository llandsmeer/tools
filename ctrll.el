;;; ctrll.el --- Location Control

;; Copyright (C) 2017 Lennart Landsmeer <lennart@landsmeer.email>

;; Permission to use, copy, modify, and distribute this software for any
;; purpose with or without fee is hereby granted, provided that the above
;; copyright notice and this permission notice appear in all copies.

;; THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
;; WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
;; MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
;; ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
;; WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
;; ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
;; OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

;; Author: L. P. L. Landsmeer <lennart@landsmeer.email>
;; Version: 1.0
;; URL: https://github.com/llandsmeer/ctrll.el

;;; Commentary:

;; This package provides location control (ctrl-l).  When the function
;; ctrll-show is called, a menu will pop up with lines from the
;; current buffer which match a certain regular expression.  The match
;; patterns are currently hardcoded per major mode.  Then a matching
;; line is selected, point will move to the corresponding line in the
;; original buffer.

;; (define-key evil-normal-state-map (kbd "C-l") 'ctrll-show)

;;; Code:

(defvar ctrll-patterns
  '(("python-mode" . "\\b\\(def\\|class\\)\\b")
    ("emacs-lisp-mode" . "\\bdef\\(un\\|const\\|var\\|ine\\)\\b")
    ("rust-mode" . "\\b\\(fn\\|struct\\|impl\\)\\b")))

(defun ctrll-search-list (key list)
  "Search for (KEY . value) in LIST and return value."
  (when list (let ((head (car list))
                   (tail (cdr list)))
               (if (equal key (car head))
                   (cdr head)
                 (ctrll-search-list key tail)))))

(make-variable-buffer-local
 (defvar ctrll-selection-mode-buffer nil))
(make-variable-buffer-local
 (defvar ctrll-selection-mode-linemap nil))

(defun ctrll-get-line-number ()
  "Return the cursor line number.  Modifies the current buffer."
  (beginning-of-line)
  (1+ (count-lines 1 (point))))

(defun ctrll-selection-mode-on-line-selected ()
  "Called when enter is pressed."
  (interactive)
  (let ((target (ctrll-search-list (ctrll-get-line-number) ctrll-selection-mode-linemap))
        (current ctrll-selection-mode-buffer))
    (kill-buffer-and-window)
    (when target (with-current-buffer current (goto-char (point-min))
                                      (forward-line (1- target))))))

(define-minor-mode ctrll-selection-mode
  "Minor mode to select the line to which the linked buffer should navigate."
  :init-value nil
  :ligher "CtrlL"
  :keymap (let ((map (make-sparse-keymap)))
            (define-key map (kbd "C-m") 'ctrll-selection-mode-on-line-selected)
            (define-key map (kbd "a") 'ctrll-selection-mode-on-line-selected)
            (define-key map (kbd "C-l") 'ctrll-selection-mode-on-line-selected)
            (define-key map (kbd "l") 'ctrll-selection-mode-on-line-selected)
            (define-key map (kbd " ") 'ctrll-selection-mode-on-line-selected)
            (define-key map (kbd "RET") 'ctrll-selection-mode-on-line-selected)
            (define-key map (kbd "<return>") 'ctrll-selection-mode-on-line-selected) map)
  :global nil
  (make-local-variable 'ctrll-selection-mode-buffer)
  (make-local-variable 'ctrll-selection-mode-linemap))

(defun ctrll-setup-menu (pattern lines)
  "Internal function to set up the ctrll menu buffer based on PATTERN, LINES and CURSOR."
  (let ((linenum-linked 0)
        (linenum-selection 0) linemap)
    (dolist (line lines)
      (setq linenum-linked (1+ linenum-linked))
      (when (string-match pattern line)
        (insert (concat line "\n"))
        (setq linenum-selection (1+ linenum-selection))
        (push (cons linenum-selection linenum-linked) linemap)))
    (ctrll-selection-mode 1)
    linemap))

(defun ctrll-show ()
  "Open location control for the current buffer."
  (interactive)
  (let ((lines (split-string (buffer-string) "\n"))
        (current (current-buffer))
        (pattern (ctrll-search-list (symbol-name major-mode) ctrll-patterns)) linemap)
    (when pattern (with-output-to-temp-buffer "*ctrll-menu*" (pop-to-buffer "*ctrll-menu*")
                                              (with-current-buffer "*ctrll-menu*"
                                                (setq linemap (ctrll-setup-menu pattern lines)))
                                              (setq ctrll-selection-mode-buffer current)
                                              (setq ctrll-selection-mode-linemap linemap)))))

(provide 'ctrll)

;;; ctrll.el ends here