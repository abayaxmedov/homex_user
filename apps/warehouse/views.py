from django.db import models, transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, permissions

from apps.accounts.models import Master
from apps.accounts.permissions import IsMaster
from apps.common.responses import success_response
from apps.common.views import EnvelopeMixin
from apps.orders.models import Order, OrderInventoryUsage
from apps.warehouse.models import MasterInventory, StockMovement, WarehouseProduct
from apps.warehouse.serializers import (
    AdminAssignInventorySerializer,
    AdminUpdateInventorySerializer,
    MasterInventorySerializer,
    UseInventorySerializer,
    WarehouseProductSerializer,
)


@extend_schema_view(get=extend_schema(tags=["Master Inventory"]))
class MasterInventoryListView(EnvelopeMixin, generics.ListAPIView):
    permission_classes = [IsMaster]
    serializer_class = MasterInventorySerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return MasterInventory.objects.none()
        queryset = MasterInventory.objects.filter(master=self.request.user).select_related("warehouse_product")
        search = self.request.query_params.get("search")
        return queryset.filter(warehouse_product__name__icontains=search) if search else queryset


@extend_schema_view(get=extend_schema(tags=["Master Inventory"]))
class MasterInventoryDetailView(EnvelopeMixin, generics.RetrieveAPIView):
    permission_classes = [IsMaster]
    serializer_class = MasterInventorySerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return MasterInventory.objects.none()
        return MasterInventory.objects.filter(master=self.request.user).select_related("warehouse_product")


@extend_schema(tags=["Master Inventory"])
class UseInventoryView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = UseInventorySerializer

    def post(self, request, pk):
        item = get_object_or_404(MasterInventory.objects.select_related("warehouse_product"), pk=pk, master=request.user)
        serializer = self.get_serializer(data=request.data, context={"item": item})
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        order = get_object_or_404(Order, id=serializer.validated_data["order_id"], master=request.user)
        unit_price = getattr(item.warehouse_product, "price", 0) or 0
        OrderInventoryUsage.objects.create(order=order, inventory=item, quantity=serializer.validated_data["quantity"], unit_price=unit_price)
        return success_response(MasterInventorySerializer(item).data)


@extend_schema_view(get=extend_schema(tags=["Master Inventory"]))
class LowStockInventoryView(EnvelopeMixin, generics.ListAPIView):
    permission_classes = [IsMaster]
    serializer_class = MasterInventorySerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return MasterInventory.objects.none()
        return MasterInventory.objects.filter(master=self.request.user, quantity__lte=models.F("low_threshold"))


@extend_schema_view(get=extend_schema(tags=["Admin Master Inventory"]), post=extend_schema(tags=["Admin Master Inventory"]))
class AdminMasterInventoryListView(EnvelopeMixin, generics.ListAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = MasterInventorySerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return MasterInventory.objects.none()
        return MasterInventory.objects.filter(master_id=self.kwargs["master_id"]).select_related("warehouse_product")

    def post(self, request, master_id):
        master = get_object_or_404(Master, id=master_id)
        serializer = AdminAssignInventorySerializer(data=request.data, context={"master": master})
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        return success_response(MasterInventorySerializer(item).data, status=201)


@extend_schema(tags=["Admin Master Inventory"])
class AdminUpdateInventoryView(generics.GenericAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = AdminUpdateInventorySerializer

    def put(self, request, master_id, item_id):
        item = get_object_or_404(MasterInventory.objects.select_related("warehouse_product"), id=item_id, master_id=master_id)
        serializer = self.get_serializer(data=request.data, context={"item": item})
        serializer.is_valid(raise_exception=True)
        return success_response(MasterInventorySerializer(serializer.save()).data)

    @transaction.atomic
    def delete(self, request, master_id, item_id):
        item = get_object_or_404(MasterInventory.objects.select_for_update(), id=item_id, master_id=master_id)
        product = item.warehouse_product
        product.quantity += item.quantity
        product.save(update_fields=["quantity", "updated_at"])
        StockMovement.objects.create(
            product=product,
            movement_type=StockMovement.IN,
            quantity=item.quantity,
            master=item.master,
            note=f"Ustadan qaytarildi: {item.master}",
        )
        item.delete()
        return success_response(message="Inventory returned", status=204)


@extend_schema_view(get=extend_schema(tags=["Admin Warehouse Products"]))
class WarehouseProductListView(EnvelopeMixin, generics.ListAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = WarehouseProductSerializer

    def get_queryset(self):
        queryset = WarehouseProduct.objects.filter(is_active=True)
        search = self.request.query_params.get("search")
        return queryset.filter(name__icontains=search) if search else queryset
