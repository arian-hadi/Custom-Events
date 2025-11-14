/**
 * File size validation for Django admin
 * Validates image uploads before form submission
 */

(function($) {
    'use strict';
    
    // Maximum file sizes in MB
    const MAX_IMAGE_SIZE_MB = 4;  // For shop product images
    const MAX_LOGO_SIZE_MB = 10;  // For site logos
    
    // Convert MB to bytes
    const MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024;
    const MAX_LOGO_SIZE_BYTES = MAX_LOGO_SIZE_MB * 1024 * 1024;
    
    /**
     * Format bytes to human readable format
     */
    function formatBytes(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
    }
    
    /**
     * Show error message in Django admin style
     */
    function showError(input, message) {
        // Remove existing error
        const existingError = input.closest('.form-row, .field-box').find('.file-size-error');
        if (existingError.length) {
            existingError.remove();
        }
        
        // Create error message
        const errorDiv = $('<div class="file-size-error" style="color: #ba2121; font-size: 0.875rem; margin-top: 5px; padding: 5px; background-color: #fff3cd; border: 1px solid #ffc107; border-radius: 3px;"></div>');
        errorDiv.text(message);
        
        // Insert after the input's parent container
        input.closest('.form-row, .field-box, .file-upload').after(errorDiv);
        
        // Add error styling to input
        input.css('border-color', '#ba2121');
    }
    
    /**
     * Remove error message
     */
    function removeError(input) {
        input.closest('.form-row, .field-box').siblings('.file-size-error').remove();
        input.css('border-color', '');
    }
    
    /**
     * Validate file size
     */
    function validateFileSize(input) {
        if (!input.files || !input.files[0]) {
            return true;
        }
        
        const file = input.files[0];
        const fileName = input.attr('name') || '';
        let maxSizeBytes;
        let maxSizeMB;
        
        // Determine max size based on field name
        if (fileName.includes('logo') || fileName.includes('favicon')) {
            maxSizeBytes = MAX_LOGO_SIZE_BYTES;
            maxSizeMB = MAX_LOGO_SIZE_MB;
        } else {
            // Default to image size for product images
            maxSizeBytes = MAX_IMAGE_SIZE_BYTES;
            maxSizeMB = MAX_IMAGE_SIZE_MB;
        }
        
        if (file.size > maxSizeBytes) {
            const fileSizeMB = (file.size / (1024 * 1024)).toFixed(2);
            const message = `File too large! Maximum size is ${maxSizeMB} MB. Your file is ${fileSizeMB} MB. Please compress or resize your image.`;
            showError(input, message);
            input.val(''); // Clear the input
            return false;
        } else {
            removeError(input);
            return true;
        }
    }
    
    /**
     * Initialize validation when document is ready
     */
    $(document).ready(function() {
        // Validate on file input change
        $(document).on('change', 'input[type="file"]', function() {
            validateFileSize($(this));
        });
        
        // Validate on form submission
        $('form').on('submit', function(e) {
            let isValid = true;
            const form = $(this);
            
            form.find('input[type="file"]').each(function() {
                if (!validateFileSize($(this))) {
                    isValid = false;
                }
            });
            
            if (!isValid) {
                e.preventDefault();
                // Scroll to first error
                const firstError = form.find('.file-size-error').first();
                if (firstError.length) {
                    $('html, body').animate({
                        scrollTop: firstError.offset().top - 100
                    }, 500);
                }
                return false;
            }
        });
        
        // Also validate existing files when page loads (for edit pages)
        $('input[type="file"]').each(function() {
            if ($(this).val()) {
                // File already selected, validate it
                validateFileSize($(this));
            }
        });
    });
    
})(django.jQuery);

