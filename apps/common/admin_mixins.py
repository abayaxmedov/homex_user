from unfold.admin import ModelAdmin, TabularInline


class HomeXModelAdmin(ModelAdmin):
    compressed_fields = True
    list_filter_submit = True
    list_fullwidth = True
    list_per_page = 30
    warn_unsaved_form = True


class HomeXTabularInline(TabularInline):
    extra = 0
    tab = True
