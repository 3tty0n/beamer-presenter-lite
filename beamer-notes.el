;;; beamer-notes.el --- Beamer slides and Markdown speaker notes side by side  -*- lexical-binding: t; -*-

;; Version: 0.1.0
;; Package-Requires: ((emacs "27.1"))
;; Keywords: tex, presentation

;;; Commentary:

;; Pairs FOO.tex with FOO.notes.md, the speaker notes read by beamer-presenter-lite.
;; In the notes, "# 4" is frame 4, "# 4.2" its second click, "# B1" the first
;; frame after \appendix.
;;
;;   M-x beamer-notes-side-by-side  open the other file beside this one and keep
;;                                  both in step as point moves (follow mode)
;;   M-x beamer-notes-edit-with-pdf the notes beside the compiled FOO.pdf (pdf-tools),
;;                                  right or below (`beamer-notes-pdf-position',
;;                                  C-u for the other; C-c C-x t switches);
;;                                  moving in the notes turns the page to that
;;                                  frame and click, turning a page scrolls the notes
;;   M-x beamer-notes-jump          go to the matching place in the other file
;;                                  (also from the PDF); add a heading if missing
;;
;; Example:
;;   (use-package beamer-notes
;;     :load-path "~/src/github.com/3tty0n/beamer-presenter-lite"
;;     :commands (beamer-notes-side-by-side beamer-notes-edit-with-pdf beamer-notes-jump)
;;     :bind (("C-c C-x n" . beamer-notes-side-by-side)
;;            ("C-c C-x p" . beamer-notes-edit-with-pdf)
;;            ("C-c C-x j" . beamer-notes-jump)))

;;; Code:

(require 'subr-x)
(require 'cl-lib)

(defgroup beamer-notes nil
  "Beamer slides and Markdown speaker notes side by side."
  :group 'tex)

(defcustom beamer-notes-pdf-position 'right
  "Where `beamer-notes-edit-with-pdf' puts the PDF: right of or below the notes."
  :type '(choice (const :tag "Right of the notes" right) (const :tag "Below the notes" below)))

(defvar-local beamer-notes--last nil "Frame key last synced from this buffer.")

(defconst beamer-notes--frame-re "^[^%\n]*?\\\\\\(appendix\\>\\|begin{frame}\\)"
  "An uncommented \\appendix or \\begin{frame}.")

(defun beamer-notes--md-p ()
  (and buffer-file-name (string-suffix-p ".notes.md" buffer-file-name)))

(defun beamer-notes--other-file ()
  (let ((f (or buffer-file-name (user-error "Buffer has no file"))))
    (if (beamer-notes--md-p)
        (concat (string-remove-suffix ".notes.md" f) ".tex")
      (concat (file-name-sans-extension f) ".notes.md"))))

(defun beamer-notes--heading-re (key)
  (format "^#[ \t]+%s\\(?:\\.[0-9-]+\\)?\\(?:[ \t]\\|$\\)" (regexp-quote key)))

;; ponytail: rescans the .tex from the top on each call; fine for talk-sized files.
(defun beamer-notes--tex-key ()
  "Key (\"N\" or \"BN\") of the frame at point in a beamer buffer."
  (save-excursion
    (let ((bound (line-end-position)) (n 0) backup)
      (goto-char (point-min))
      (while (re-search-forward beamer-notes--frame-re bound t)
        (if (equal (match-string 1) "appendix")
            (setq n 0 backup t)
          (setq n (1+ n))))
      (format "%s%d" (if backup "B" "") (max n 1)))))

(defconst beamer-notes--section-re
  "^#[ \t]+\\(B?[0-9]+\\)\\(?:\\.\\([0-9]+\\)\\(?:-\\([0-9]+\\)\\)?\\)?\\(?:[ \t]\\|$\\)"
  "A notes heading: 1 = frame key, 2 = first click, 3 = last click.")

(defun beamer-notes--md-section ()
  "(FRAME FIRST-CLICK) of the notes section at point (click nil = all), or nil."
  (save-excursion
    (end-of-line)
    (when (re-search-backward beamer-notes--section-re nil t)
      (list (match-string 1) (and (match-string 2) (string-to-number (match-string 2)))))))

(defun beamer-notes--md-key ()
  "Key of the notes section at point, or nil."
  (car (beamer-notes--md-section)))

(defun beamer-notes--key ()
  (if (beamer-notes--md-p) (beamer-notes--md-key) (beamer-notes--tex-key)))

(defun beamer-notes--goto (key)
  "Move to KEY in the current buffer; return non-nil when found."
  (let ((pos (save-excursion
               (goto-char (point-min))
               (if (beamer-notes--md-p)
                   (and (re-search-forward (beamer-notes--heading-re key) nil t)
                        (line-beginning-position))
                 (let ((backup (string-prefix-p "B" key))
                       (want (string-to-number (string-remove-prefix "B" key)))
                       (n 0) in-backup found)
                   (while (and (not found) (re-search-forward beamer-notes--frame-re nil t))
                     (if (equal (match-string 1) "appendix")
                         (setq in-backup t n 0)
                       (setq n (1+ n))
                       (when (and (eq backup in-backup) (= n want))
                         (setq found (line-beginning-position)))))
                   found)))))
    (when pos (goto-char pos))))

(defun beamer-notes--add-heading (key)
  "Insert \"# KEY\" before the first section of a later frame (or at the end)."
  (let ((rank (lambda (k) (+ (if (string-prefix-p "B" k) 10000 0)
                             (string-to-number (string-remove-prefix "B" k))))))
    (goto-char (point-min))
    (while (and (re-search-forward "^#[ \t]+\\(B?[0-9]+\\)" nil 'move)
                (<= (funcall rank (match-string 1)) (funcall rank key))))
    (unless (eobp) (beginning-of-line))
    (unless (bolp) (insert "\n"))
    (insert "# " key "\n\n\n")
    (forward-line -2)))

(defun beamer-notes--show (key &optional select add)
  "Show KEY in the other file's window.
Select that window when SELECT; ADD a missing notes heading."
  (let* ((buf (find-file-noselect (beamer-notes--other-file)))
         (win (or (get-buffer-window buf) (display-buffer buf t))))
    (with-selected-window win
      (cond ((beamer-notes--goto key) (recenter 0))
            ((and add (beamer-notes--md-p)) (beamer-notes--add-heading key) (recenter 1))
            (t (message "No notes for frame %s" key))))
    (when select (select-window win))))

;;; The compiled PDF (FOO.pdf, via pdf-tools)

(eval-when-compile (require 'pdf-view nil t))
(declare-function pdf-info-pagelabels "pdf-info")
(declare-function pdf-view-goto-page "pdf-view")
(declare-function pdf-view-fit-page-to-window "pdf-view")
(declare-function image-mode-window-get "image-mode")
(defvar beamer-notes--syncing nil "Non-nil while this package moves a window itself.")

(defun beamer-notes--pdf-file ()
  (let ((f (or buffer-file-name (user-error "Buffer has no file"))))
    (concat (if (beamer-notes--md-p) (string-remove-suffix ".notes.md" f) (file-name-sans-extension f))
            ".pdf")))

(defun beamer-notes--page-keys (pdf)
  "(FRAME . CLICK) for each page of PDF, from beamer's page labels (= frame number).
Frames after the numbering restarts (appendixnumberbeamer) get a B prefix."
  (require 'pdf-info)
  (let (keys prev backup (click 0))
    (dolist (label (pdf-info-pagelabels pdf) (nreverse keys))
      (if (equal label prev)
          (setq click (1+ click))
        (setq click 1)
        (when (and prev (string-match-p "\\`[0-9]+\\'" label) (string-match-p "\\`[0-9]+\\'" prev)
                   (< (string-to-number label) (string-to-number prev)))
          (setq backup t)))
      (setq prev label)
      (push (cons (concat (if backup "B" "") label) click) keys))))

(defun beamer-notes--md-goto-page-key (frame click)
  "Move to the notes for FRAME's CLICK: its own section, else the frame-wide one."
  (let (exact wide any)
    (save-excursion
      (goto-char (point-min))
      (while (re-search-forward beamer-notes--section-re nil t)
        (when (equal (match-string 1) frame)
          (let* ((lo (and (match-string 2) (string-to-number (match-string 2))))
                 (hi (if (match-string 3) (string-to-number (match-string 3)) lo))
                 (p (line-beginning-position)))
            (cond ((null lo) (setq wide (or wide p)))
                  ((<= lo click hi) (setq exact (or exact p))))
            (setq any (or any p))))))
    (let ((p (or exact wide any)))
      (when p (goto-char p)))))

(defun beamer-notes--pdf-show (section)
  "Turn the visible FOO.pdf to the first page of SECTION (FRAME CLICK)."
  (let* ((buf (find-buffer-visiting (beamer-notes--pdf-file)))
         (win (and buf (get-buffer-window buf))))
    (when win
      (let* ((keys (beamer-notes--page-keys (buffer-file-name buf)))
             (page (or (cl-position (cons (car section) (or (cadr section) 1)) keys :test #'equal)
                       (cl-position (car section) keys :key #'car :test #'equal))))
        (when page
          (let ((beamer-notes--syncing t))
            (with-selected-window win (pdf-view-goto-page (1+ page)))))))))

(defun beamer-notes--pdf-page-key ()
  (nth (1- (pdf-view-current-page)) (beamer-notes--page-keys buffer-file-name)))

(defun beamer-notes--pdf-sync ()
  "After a page change in FOO.pdf, show that page's notes in the notes window."
  (unless beamer-notes--syncing
    (let* ((key (beamer-notes--pdf-page-key))
           (buf (find-buffer-visiting (beamer-notes--other-file)))
           (win (and key buf (get-buffer-window buf))))
      (when win
        (with-selected-window win
          (if (beamer-notes--md-goto-page-key (car key) (cdr key))
              (progn (recenter 0) (setq beamer-notes--last (beamer-notes--md-section)))
            (message "No notes for frame %s, click %d (M-x beamer-notes-jump adds them)"
                     (car key) (cdr key))))))))

(defvar beamer-notes-mode-map
  (let ((map (make-sparse-keymap)))
    (define-key map (kbd "C-c C-x t") #'beamer-notes-toggle-pdf-position)
    map)
  "Keys of the follow modes, in the notes and in the PDF.")

(define-minor-mode beamer-notes-pdf-follow-mode
  "In FOO.pdf, keep the FOO.notes.md window on the notes of the current page."
  :lighter " BNotes"
  :keymap beamer-notes-mode-map
  (if beamer-notes-pdf-follow-mode
      (add-hook 'pdf-view-after-change-page-hook #'beamer-notes--pdf-sync nil t)
    (remove-hook 'pdf-view-after-change-page-hook #'beamer-notes--pdf-sync t)))

(defun beamer-notes--pdf-jump ()
  "From a FOO.pdf page, go to its notes; add \"# N\" (or \"# N.k\") if missing."
  (let* ((key (or (beamer-notes--pdf-page-key) (user-error "No page label")))
         (clicks (cl-count (car key) (beamer-notes--page-keys buffer-file-name) :key #'car :test #'equal))
         (buf (find-file-noselect (beamer-notes--other-file)))
         (win (or (get-buffer-window buf) (display-buffer buf t))))
    (select-window win)
    (if (beamer-notes--md-goto-page-key (car key) (cdr key))
        (recenter 0)
      (beamer-notes--add-heading (if (> clicks 1) (format "%s.%d" (car key) (cdr key)) (car key)))
      (recenter 1))))

;;;###autoload
(defun beamer-notes-edit-with-pdf (&optional position)
  "Edit FOO.notes.md beside the compiled FOO.pdf (pdf-tools), both kept in step.
The PDF goes to POSITION, `right' or `below': by default
`beamer-notes-pdf-position', with a prefix argument the other one.
Works from the notes, the .tex or the PDF."
  (interactive (list (if current-prefix-arg
                         (if (eq beamer-notes-pdf-position 'below) 'right 'below)
                       beamer-notes-pdf-position)))
  (require 'pdf-tools)
  (let* ((md (if (beamer-notes--md-p) (current-buffer) (find-file-noselect (beamer-notes--other-file))))
         (pdf (find-file-noselect (with-current-buffer md (beamer-notes--pdf-file)))))
    (delete-other-windows)
    (switch-to-buffer md)
    (let ((win (if (eq position 'below) (split-window-below) (split-window-right))))
      (set-window-buffer win pdf)
      (with-selected-window win (pdf-view-fit-page-to-window)))   ; whole slide in either shape
    (with-current-buffer pdf (beamer-notes-pdf-follow-mode 1))
    (beamer-notes-follow-mode 1)
    (setq beamer-notes--last nil)
    (beamer-notes--sync)))

;;;###autoload
(defun beamer-notes-toggle-pdf-position ()
  "Move the FOO.pdf window from right of the notes to below them, or back.
The choice is kept in `beamer-notes-pdf-position' for this session."
  (interactive)
  (let* ((md (find-buffer-visiting (if (beamer-notes--md-p) buffer-file-name (beamer-notes--other-file))))
         (mwin (and md (get-buffer-window md)))
         (pdf (and md (find-buffer-visiting (with-current-buffer md (beamer-notes--pdf-file)))))
         (pwin (and pdf (get-buffer-window pdf))))
    (unless (and mwin pwin)
      (user-error "Show the notes and the PDF first (M-x beamer-notes-edit-with-pdf)"))
    (setq beamer-notes-pdf-position (if (eq (window-in-direction 'below mwin) pwin) 'right 'below))
    (let ((selected (eq (selected-window) pwin))
          (page (with-selected-window pwin (pdf-view-current-page)))
          (beamer-notes--syncing t))
      (delete-window pwin)
      (setq pwin (split-window mwin nil beamer-notes-pdf-position))
      (set-window-buffer pwin pdf)
      (with-selected-window pwin
        (pdf-view-goto-page page)
        (pdf-view-fit-page-to-window))
      (select-window (if selected pwin mwin)))))

;;;###autoload
(defun beamer-notes-jump ()
  "Jump between a beamer frame (.tex or PDF) and its notes in FOO.notes.md."
  (interactive)
  (if (derived-mode-p 'pdf-view-mode)
      (beamer-notes--pdf-jump)
    (let ((key (or (beamer-notes--key) (user-error "Not inside a notes section"))))
      (beamer-notes--show key t t))))

(defun beamer-notes--sync ()
  (let ((state (if (beamer-notes--md-p) (beamer-notes--md-section) (beamer-notes--key))))
    (when (and state (not (equal state beamer-notes--last)))
      (setq beamer-notes--last state)
      (let ((buf (find-buffer-visiting (beamer-notes--other-file))))
        (when (and buf (get-buffer-window buf))
          (beamer-notes--show (if (consp state) (car state) state))))
      (when (consp state)
        (beamer-notes--pdf-show state)))))

;;;###autoload
(define-minor-mode beamer-notes-follow-mode
  "Keep the paired slides/notes window on the frame at point."
  :lighter " BNotes"
  :keymap beamer-notes-mode-map
  (if beamer-notes-follow-mode
      (add-hook 'post-command-hook #'beamer-notes--sync nil t)
    (remove-hook 'post-command-hook #'beamer-notes--sync t)))

;;;###autoload
(defun beamer-notes-side-by-side ()
  "Show the slides and their notes side by side and keep them in step."
  (interactive)
  (let ((key (beamer-notes--key))
        (other (find-file-noselect (beamer-notes--other-file))))
    (delete-other-windows)
    (set-window-buffer (split-window-right) other)
    (beamer-notes-follow-mode 1)
    (with-current-buffer other (beamer-notes-follow-mode 1))
    (setq beamer-notes--last nil)
    (when key (beamer-notes--show key))))

(provide 'beamer-notes)
;;; beamer-notes.el ends here
